"""Duplicate ticket detection and merge."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session_context
from app.models import Ticket, TicketMessage, TicketStatus, utcnow
from app.services.audit import log_ticket_event
from app.services.embeddings import cosine_similarity

settings = get_settings()


def detect_duplicates(ticket_id: UUID, session: Session | None = None) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket or not ticket.embedding:
            return {"merged": False, "reason": "no_ticket_or_embedding"}

        since = utcnow() - timedelta(hours=48)
        candidates = session.exec(
            select(Ticket).where(
                Ticket.tenant_id == ticket.tenant_id,
                Ticket.customer_email == ticket.customer_email,
                Ticket.id != ticket.id,
                Ticket.created_at >= since,
                Ticket.merged_into_id.is_(None),  # type: ignore
                Ticket.status != TicketStatus.merged,
            )
        ).all()

        best = None
        best_score = 0.0
        for other in candidates:
            if not other.embedding:
                continue
            score = cosine_similarity(ticket.embedding, other.embedding)
            if score > best_score:
                best_score = score
                best = other

        if not best or best_score < settings.similarity_threshold:
            return {"merged": False, "best_score": best_score}

        # Merge newer into older
        if ticket.created_at >= best.created_at:
            survivor, duplicate = best, ticket
        else:
            survivor, duplicate = ticket, best

        note = TicketMessage(
            tenant_id=survivor.tenant_id,
            ticket_id=survivor.id,
            author_type="system",
            body=f"Merged duplicate ticket {duplicate.id} (similarity={best_score:.2f}): {duplicate.subject}\n\n{duplicate.body}",
            is_internal=True,
        )
        duplicate.status = TicketStatus.merged
        duplicate.merged_into_id = survivor.id
        duplicate.updated_at = utcnow()
        survivor.updated_at = utcnow()
        session.add(note)
        session.add(duplicate)
        session.add(survivor)
        session.commit()

        log_ticket_event(
            session,
            tenant_id=survivor.tenant_id,
            ticket_id=survivor.id,
            action="duplicate_merged",
            actor_type="ai",
            details={
                "duplicate_id": str(duplicate.id),
                "similarity": best_score,
            },
        )
        log_ticket_event(
            session,
            tenant_id=duplicate.tenant_id,
            ticket_id=duplicate.id,
            action="merged_into",
            actor_type="ai",
            details={"survivor_id": str(survivor.id), "similarity": best_score},
        )
        return {
            "merged": True,
            "survivor_id": str(survivor.id),
            "duplicate_id": str(duplicate.id),
            "similarity": best_score,
        }
    finally:
        if owns:
            session.close()
