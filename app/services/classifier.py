"""Ticket classification + sentiment analysis."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session, select

from app.db import get_session_context
from app.models import Alert, SentimentTone, Ticket, TicketPriority, utcnow
from app.services.audit import log_ticket_event
from app.services.claude import get_claude

logger = logging.getLogger(__name__)


def classify_ticket(ticket_id: UUID, session: Session | None = None) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return {"error": "ticket_not_found"}

        claude = get_claude()
        result = claude.complete_json(
            system=(
                "You are a support ticket classifier for a multi-tenant helpdesk. "
                "Classify category, priority (low|medium|high|urgent), and suggested_team."
            ),
            user=f"Subject: {ticket.subject}\n\nBody: {ticket.body}",
            fallback={
                "category": "general",
                "priority": "medium",
                "suggested_team": "support",
                "confidence": 0.4,
            },
        )

        priority = str(result.get("priority", "medium")).lower()
        if priority not in {p.value for p in TicketPriority}:
            priority = TicketPriority.medium.value

        ticket.category = str(result.get("category", "general"))[:120]
        ticket.priority = TicketPriority(priority)
        ticket.assigned_team = str(result.get("suggested_team", "support"))[:120]
        ticket.updated_at = utcnow()
        session.add(ticket)
        session.commit()
        session.refresh(ticket)

        log_ticket_event(
            session,
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            action="classified",
            actor_type="ai",
            details=result,
        )

        if ticket.priority == TicketPriority.urgent:
            from app.services.escalation import route_escalation

            route_escalation(ticket.id, session=session)

        return result
    finally:
        if owns:
            session.close()


def analyze_sentiment(ticket_id: UUID, session: Session | None = None) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return {"error": "ticket_not_found"}

        claude = get_claude()
        result = claude.complete_json(
            system=(
                "Analyze customer sentiment. Return sentiment as neutral|frustrated|angry "
                "and sentiment_score from 0 to 1."
            ),
            user=f"Subject: {ticket.subject}\n\nBody: {ticket.body}",
            fallback={"sentiment": "neutral", "sentiment_score": 0.2},
        )

        tone = str(result.get("sentiment", "neutral")).lower()
        if tone not in {t.value for t in SentimentTone}:
            tone = SentimentTone.neutral.value
        score = float(result.get("sentiment_score", 0.2))
        score = max(0.0, min(1.0, score))

        ticket.sentiment = SentimentTone(tone)
        ticket.sentiment_score = score
        ticket.updated_at = utcnow()

        if tone == SentimentTone.angry.value and ticket.priority in (
            TicketPriority.high,
            TicketPriority.urgent,
        ):
            ticket.priority = TicketPriority.urgent
            alert = Alert(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                alert_type="angry_escalation",
                message=f"Angry high-priority ticket from {ticket.customer_email}",
                severity="critical",
            )
            session.add(alert)
            log_ticket_event(
                session,
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                action="sentiment_escalated",
                actor_type="ai",
                details={"sentiment": tone, "score": score},
            )
            try:
                from app.services.realtime import broadcast_tenant

                broadcast_tenant(
                    str(ticket.tenant_id),
                    {"type": "alert", "ticket_id": str(ticket.id), "message": alert.message},
                )
            except Exception:
                pass

        session.add(ticket)
        session.commit()
        session.refresh(ticket)

        log_ticket_event(
            session,
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            action="sentiment_analyzed",
            actor_type="ai",
            details={"sentiment": tone, "score": score},
        )
        return {"sentiment": tone, "sentiment_score": score}
    finally:
        if owns:
            session.close()
