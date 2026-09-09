"""Knowledge base auto-updater from recurring unresolved issues."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session_context
from app.models import KBArticle, Ticket, TicketStatus, utcnow
from app.services.claude import get_claude
from app.services.embeddings import cosine_similarity, embed_text
from app.services.similarity import embed_kb_article

settings = get_settings()


def maybe_draft_kb_from_unresolved(tenant_id: UUID, session: Session | None = None) -> list[dict]:
    """
    If 3+ similar unresolved tickets exist with no matching KB article,
    auto-draft a KBArticle for admin review.
    """
    owns = session is None
    session = session or get_session_context()
    drafted: list[dict] = []
    try:
        open_tickets = session.exec(
            select(Ticket).where(
                Ticket.tenant_id == tenant_id,
                Ticket.status.in_(  # type: ignore[attr-defined]
                    [TicketStatus.open, TicketStatus.pending, TicketStatus.in_progress]
                ),
                Ticket.merged_into_id.is_(None),  # type: ignore[attr-defined]
            )
        ).all()

        # Cluster by category + embedding similarity
        by_category: dict[str, list[Ticket]] = defaultdict(list)
        for t in open_tickets:
            by_category[t.category or "general"].append(t)

        kb_articles = session.exec(
            select(KBArticle).where(KBArticle.tenant_id == tenant_id)
        ).all()

        for category, tickets in by_category.items():
            if len(tickets) < 3:
                continue
            # Find a cluster of 3+ similar tickets
            used: set[UUID] = set()
            for seed in tickets:
                if seed.id in used or not seed.embedding:
                    continue
                cluster = [seed]
                for other in tickets:
                    if other.id == seed.id or other.id in used or not other.embedding:
                        continue
                    if cosine_similarity(seed.embedding, other.embedding) >= 0.75:
                        cluster.append(other)
                if len(cluster) < 3:
                    continue

                # Skip if a published/pending KB already covers this
                covered = False
                seed_emb = seed.embedding
                for article in kb_articles:
                    emb = article.embedding or embed_text(f"{article.title}\n{article.content}")
                    if cosine_similarity(seed_emb, emb) >= settings.similarity_threshold:
                        covered = True
                        break
                if covered:
                    continue

                claude = get_claude()
                sample = "\n\n".join(
                    f"Subject: {t.subject}\nBody: {t.body[:500]}" for t in cluster[:5]
                )
                draft = claude.complete_json(
                    system=(
                        "Draft a concise knowledge base article that would help customers "
                        "self-serve this recurring issue. Return title, content, category, tags."
                    ),
                    user=sample,
                    fallback={
                        "title": f"How to resolve {category} issues",
                        "content": "Auto-drafted from recurring tickets. Needs admin review.",
                        "category": category,
                        "tags": [category, "auto-draft"],
                    },
                )
                article = KBArticle(
                    tenant_id=tenant_id,
                    title=str(draft.get("title", f"Draft: {category}"))[:200],
                    content=str(draft.get("content", "")),
                    category=str(draft.get("category", category)),
                    tags=list(draft.get("tags") or [category]),
                    status="pending_review",
                    source_ticket_ids=[str(t.id) for t in cluster],
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
                session.add(article)
                session.commit()
                session.refresh(article)
                embed_kb_article(article.id, session=session)
                for t in cluster:
                    used.add(t.id)
                drafted.append({"id": str(article.id), "title": article.title, "cluster_size": len(cluster)})
                kb_articles.append(article)

        return drafted
    finally:
        if owns:
            session.close()
