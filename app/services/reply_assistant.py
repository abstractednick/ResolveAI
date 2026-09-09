"""First-response and agent reply drafting."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from app.db import get_session_context
from app.models import Ticket, TicketMessage, utcnow
from app.services.audit import log_ticket_event
from app.services.claude import get_claude
from app.services.similarity import find_kb_article, find_similar_tickets


def _build_context(ticket: Ticket, session: Session) -> str:
    similar = find_similar_tickets(ticket.id, session=session, limit=3)
    kb = find_kb_article(ticket.id, session=session)
    parts = [
        f"Subject: {ticket.subject}",
        f"Body: {ticket.body}",
        f"Category: {ticket.category}",
        f"Priority: {ticket.priority}",
        f"Language: {ticket.language}",
    ]
    if kb:
        parts.append(f"KB Article: {kb['title']}\n{kb['content'][:1200]}")
    if similar:
        parts.append("Similar resolved tickets:\n" + "\n".join(
            f"- {s['subject']} (sim={s['similarity']})" for s in similar
        ))
    return "\n\n".join(parts)


def generate_first_response(ticket_id: UUID, session: Session | None = None, *, auto_send: bool = False) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return {"error": "not_found"}

        claude = get_claude()
        context = _build_context(ticket, session)
        draft = claude.complete(
            system=(
                "You are a helpful support agent. Draft a concise, empathetic first response. "
                "Use KB/similar ticket context when relevant. Do not invent policy."
            ),
            user=context,
        )

        ticket.suggested_reply = draft
        ticket.updated_at = utcnow()

        if auto_send or ticket.auto_resolved:
            from app.services.translator import translate_outgoing

            outbound = translate_outgoing(draft, ticket.language) if ticket.language != "en" else draft
            msg = TicketMessage(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                author_type="ai",
                body=outbound,
                body_original=draft if ticket.language != "en" else None,
                language=ticket.language,
            )
            session.add(msg)
            ticket.first_response_sent = True
            ticket.first_responded_at = utcnow()

        session.add(ticket)
        session.commit()
        log_ticket_event(
            session,
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            action="first_response_drafted",
            actor_type="ai",
            details={"auto_send": auto_send or ticket.auto_resolved, "draft": draft[:500]},
        )
        return {"draft": draft, "sent": bool(auto_send or ticket.auto_resolved)}
    finally:
        if owns:
            session.close()


def generate_agent_draft(ticket_id: UUID, session: Session | None = None) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return {"error": "not_found"}
        claude = get_claude()
        draft = claude.complete(
            system=(
                "Draft a reply for a human agent to review and send. Be accurate, concise, "
                "and include clear next steps."
            ),
            user=_build_context(ticket, session),
        )
        ticket.suggested_reply = draft
        ticket.updated_at = utcnow()
        session.add(ticket)
        session.commit()
        log_ticket_event(
            session,
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            action="agent_draft_generated",
            actor_type="ai",
            details={"draft": draft[:500]},
        )
        return {"draft": draft}
    finally:
        if owns:
            session.close()
