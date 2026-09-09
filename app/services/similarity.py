"""Similar ticket matching and KB search via embeddings."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session_context
from app.models import KBArticle, Ticket, TicketStatus, utcnow
from app.services.audit import log_ticket_event
from app.services.embeddings import cosine_similarity, embed_text

settings = get_settings()


def embed_ticket(ticket_id: UUID, session: Session | None = None) -> list[float]:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return []
        vector = embed_text(f"{ticket.subject}\n{ticket.body}")
        ticket.embedding = vector
        ticket.updated_at = utcnow()
        session.add(ticket)
        session.commit()
        return vector
    finally:
        if owns:
            session.close()


def embed_kb_article(article_id: UUID, session: Session | None = None) -> list[float]:
    owns = session is None
    session = session or get_session_context()
    try:
        article = session.get(KBArticle, article_id)
        if not article:
            return []
        vector = embed_text(f"{article.title}\n{article.content}")
        article.embedding = vector
        article.updated_at = utcnow()
        session.add(article)
        session.commit()
        return vector
    finally:
        if owns:
            session.close()


def find_similar_tickets(ticket_id: UUID, session: Session | None = None, limit: int = 5) -> list[dict]:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return []
        vector = ticket.embedding or embed_ticket(ticket_id, session=session)
        if not vector:
            return []

        candidates = session.exec(
            select(Ticket).where(
                Ticket.tenant_id == ticket.tenant_id,
                Ticket.id != ticket.id,
                Ticket.status == TicketStatus.resolved,
                Ticket.merged_into_id.is_(None),  # type: ignore[attr-defined]
            )
        ).all()

        scored: list[tuple[float, Ticket]] = []
        for other in candidates:
            if not other.embedding:
                continue
            score = cosine_similarity(vector, other.embedding)
            scored.append((score, other))
        scored.sort(key=lambda x: x[0], reverse=True)

        results = [
            {
                "id": str(t.id),
                "subject": t.subject,
                "category": t.category,
                "similarity": round(score, 4),
                "summary": t.summary,
            }
            for score, t in scored[:limit]
        ]
        log_ticket_event(
            session,
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            action="similar_tickets_found",
            actor_type="ai",
            details={"matches": results},
        )
        return results
    finally:
        if owns:
            session.close()


def find_kb_article(ticket_id: UUID, session: Session | None = None) -> dict | None:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return None
        vector = ticket.embedding or embed_ticket(ticket_id, session=session)
        articles = session.exec(
            select(KBArticle).where(
                KBArticle.tenant_id == ticket.tenant_id,
                KBArticle.status == "published",
            )
        ).all()
        best = None
        best_score = 0.0
        for article in articles:
            emb = article.embedding or embed_text(f"{article.title}\n{article.content}")
            if not article.embedding:
                article.embedding = emb
                session.add(article)
            score = cosine_similarity(vector, emb)
            if score > best_score:
                best_score = score
                best = article
        session.commit()
        if best and best_score >= settings.similarity_threshold:
            return {
                "id": str(best.id),
                "title": best.title,
                "content": best.content,
                "similarity": round(best_score, 4),
            }
        return None
    finally:
        if owns:
            session.close()
