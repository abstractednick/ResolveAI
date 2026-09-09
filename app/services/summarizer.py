"""Thread summarization for agent handoffs."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session, select

from app.db import get_session_context
from app.models import Ticket, TicketMessage, utcnow
from app.services.audit import log_ticket_event
from app.services.claude import get_claude


def summarize_thread(ticket_id: UUID, session: Session | None = None) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return {"error": "not_found"}

        messages = session.exec(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at)  # type: ignore
        ).all()
        thread = [f"Customer: {ticket.subject}\n{ticket.body}"]
        for m in messages:
            thread.append(f"{m.author_type}: {m.body}")

        claude = get_claude()
        summary = claude.complete(
            system=(
                "Summarize this support thread in 2-3 short lines for an agent handoff. "
                "Include issue, actions taken, and open questions."
            ),
            user="\n\n".join(thread)[:8000],
        )
        ticket.summary = summary
        ticket.updated_at = utcnow()
        session.add(ticket)
        session.commit()
        log_ticket_event(
            session,
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            action="summarized",
            actor_type="ai",
            details={"summary": summary},
        )
        return {"summary": summary}
    finally:
        if owns:
            session.close()
