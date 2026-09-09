"""CSAT prediction and proactive follow-up triggers."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from app.config import get_settings
from app.db import get_session_context
from app.models import Alert, Ticket, TicketMessage, utcnow
from app.services.audit import log_ticket_event
from app.services.claude import get_claude

settings = get_settings()


def predict_csat(ticket_id: UUID, session: Session | None = None) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return {"error": "not_found"}

        claude = get_claude()
        result = claude.complete_json(
            system=(
                "Predict customer satisfaction (0-1) from resolution tone and wait time. "
                "Return {predicted_csat, reason, should_follow_up}."
            ),
            user=(
                f"Priority: {ticket.priority}\nSentiment: {ticket.sentiment} ({ticket.sentiment_score})\n"
                f"Created: {ticket.created_at}\nResolved: {ticket.resolved_at}\n"
                f"Auto-resolved: {ticket.auto_resolved}\nSubject: {ticket.subject}\nBody: {ticket.body[:1000]}"
            ),
            fallback=None,
        )

        if not result:
            # Heuristic
            score = 0.75
            score -= min(0.35, ticket.sentiment_score * 0.4)
            if ticket.breach_risk_score > 0.7:
                score -= 0.2
            if ticket.auto_resolved:
                score += 0.05
            result = {
                "predicted_csat": max(0.0, min(1.0, score)),
                "reason": "heuristic",
                "should_follow_up": score < settings.csat_low_threshold,
            }

        predicted = float(result.get("predicted_csat", 0.7))
        predicted = max(0.0, min(1.0, predicted))
        ticket.predicted_csat = predicted
        ticket.updated_at = utcnow()
        session.add(ticket)
        session.commit()

        follow_up = bool(result.get("should_follow_up")) or predicted < settings.csat_low_threshold
        if follow_up:
            msg = TicketMessage(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                author_type="ai",
                body=(
                    "Hi — we wanted to check in before our survey goes out. "
                    "Was everything resolved to your satisfaction? Reply here and we'll help right away."
                ),
                is_internal=False,
            )
            alert = Alert(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                alert_type="low_csat_risk",
                message=f"Predicted CSAT {predicted:.0%} — proactive follow-up sent",
                severity="info",
            )
            session.add(msg)
            session.add(alert)
            session.commit()

        log_ticket_event(
            session,
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            action="csat_predicted",
            actor_type="ai",
            details={"predicted_csat": predicted, "follow_up": follow_up, **result},
        )
        return {"predicted_csat": predicted, "follow_up": follow_up}
    finally:
        if owns:
            session.close()
