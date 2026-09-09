"""Public self-service deflection widget API."""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.middleware.rate_limit import rate_limit_dependency
from app.models import KBArticle, Tenant, Ticket, TicketChannel, TicketMessage, TicketStatus
from app.schemas import WidgetAnswer, WidgetQuery
from app.services.claude import get_claude
from app.services.embeddings import cosine_similarity, embed_text
from app.services.sanitize import sanitize_text
from app.workers.tasks import enqueue_ticket_processing
from app.config import get_settings

router = APIRouter(prefix="/widget", tags=["widget"], dependencies=[Depends(rate_limit_dependency)])
settings = get_settings()


def _tenant(session: Session, key: str | None) -> Tenant:
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-Tenant-Key")
    tenant = session.exec(select(Tenant).where(Tenant.api_key == key)).first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid tenant key")
    return tenant


@router.post("/query", response_model=WidgetAnswer)
def widget_query(
    payload: WidgetQuery,
    session: Session = Depends(get_session),
    x_tenant_key: str | None = Header(default=None, alias="X-Tenant-Key"),
):
    tenant = _tenant(session, x_tenant_key)
    question = sanitize_text(payload.question, max_length=2000)
    q_emb = embed_text(question)

    articles = session.exec(
        select(KBArticle).where(KBArticle.tenant_id == tenant.id, KBArticle.status == "published")
    ).all()
    best_article = None
    best_score = 0.0
    for article in articles:
        emb = article.embedding or embed_text(f"{article.title}\n{article.content}")
        score = cosine_similarity(q_emb, emb)
        if score > best_score:
            best_score = score
            best_article = article

    similar_ids = []
    resolved = session.exec(
        select(Ticket).where(
            Ticket.tenant_id == tenant.id,
            Ticket.status == TicketStatus.resolved,
        ).limit(100)
    ).all()
    scored = []
    for t in resolved:
        if not t.embedding:
            continue
        scored.append((cosine_similarity(q_emb, t.embedding), t))
    scored.sort(key=lambda x: x[0], reverse=True)
    similar_ids = [t.id for score, t in scored[:3] if score >= 0.6]

    answered = False
    answer = None
    confidence = best_score
    if best_article and best_score >= settings.similarity_threshold:
        claude = get_claude()
        answer = claude.complete(
            system="Answer the customer using the KB article. Be concise. If unsure, say so.",
            user=f"Question: {question}\n\nKB: {best_article.title}\n{best_article.content[:2000]}",
        )
        answered = True
    else:
        # Ask Claude if it can answer briefly from similar context
        claude = get_claude()
        result = claude.complete_json(
            system="Decide if you can answer. Return {answered, answer, confidence}.",
            user=f"Question: {question}",
            fallback={"answered": False, "answer": None, "confidence": 0.2},
        )
        answered = bool(result.get("answered"))
        answer = result.get("answer")
        confidence = float(result.get("confidence", confidence))

    ticket_id = None
    if (not answered or payload.create_ticket_if_unresolved) and payload.create_ticket_if_unresolved:
        email = str(payload.customer_email or "widget@unknown.local")
        ticket = Ticket(
            tenant_id=tenant.id,
            customer_email=email.lower(),
            subject=question[:120],
            body=question,
            channel=TicketChannel.widget,
        )
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        session.add(
            TicketMessage(
                tenant_id=tenant.id,
                ticket_id=ticket.id,
                author_type="customer",
                body=question,
            )
        )
        session.commit()
        enqueue_ticket_processing(ticket.id)
        ticket_id = ticket.id

    return WidgetAnswer(
        answered=answered,
        answer=answer,
        kb_article_id=best_article.id if best_article and answered else None,
        similar_ticket_ids=similar_ids,
        ticket_id=ticket_id,
        confidence=confidence,
    )
