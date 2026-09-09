"""SLA breach risk prediction."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session_context
from app.models import Alert, SLAPolicy, Ticket, TicketStatus, utcnow
from app.services.audit import log_ticket_event

settings = get_settings()


def _minutes_since(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 60.0


def get_default_sla(session: Session, tenant_id: UUID) -> SLAPolicy | None:
    return session.exec(
        select(SLAPolicy).where(SLAPolicy.tenant_id == tenant_id, SLAPolicy.is_default == True)  # noqa: E712
    ).first()


def compute_breach_risk(ticket: Ticket, policy: SLAPolicy | None, queue_load: int) -> float:
    targets = (policy.response_targets if policy else {"low": 480, "medium": 240, "high": 60, "urgent": 15})
    target = float(targets.get(ticket.priority.value if hasattr(ticket.priority, "value") else ticket.priority, 240))
    elapsed = _minutes_since(ticket.created_at)
    ratio = elapsed / max(target, 1.0)
    load_factor = min(0.25, queue_load / 100.0)
    priority_boost = {"low": 0.0, "medium": 0.05, "high": 0.1, "urgent": 0.15}.get(
        ticket.priority.value if hasattr(ticket.priority, "value") else str(ticket.priority), 0.05
    )
    sentiment_boost = 0.1 if ticket.sentiment_score >= 0.7 else 0.0
    risk = min(1.0, max(0.0, ratio * 0.75 + load_factor + priority_boost + sentiment_boost))
    return round(risk, 4)


def predict_sla_for_ticket(ticket_id: UUID, session: Session | None = None) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return {"error": "not_found"}
        open_count = len(
            session.exec(
                select(Ticket).where(
                    Ticket.tenant_id == ticket.tenant_id,
                    Ticket.status.in_([TicketStatus.open, TicketStatus.in_progress, TicketStatus.pending]),  # type: ignore
                )
            ).all()
        )
        policy = get_default_sla(session, ticket.tenant_id)
        risk = compute_breach_risk(ticket, policy, open_count)
        ticket.breach_risk_score = risk
        ticket.updated_at = utcnow()
        session.add(ticket)
        session.commit()
        return {"ticket_id": str(ticket.id), "breach_risk_score": risk, "queue_load": open_count}
    finally:
        if owns:
            session.close()


def scan_sla_risks(tenant_id: UUID | None = None, session: Session | None = None) -> list[dict]:
    owns = session is None
    session = session or get_session_context()
    flagged: list[dict] = []
    try:
        q = select(Ticket).where(
            Ticket.status.in_([TicketStatus.open, TicketStatus.in_progress, TicketStatus.pending]),  # type: ignore
            Ticket.merged_into_id.is_(None),  # type: ignore
        )
        if tenant_id:
            q = q.where(Ticket.tenant_id == tenant_id)
        tickets = session.exec(q).all()
        for ticket in tickets:
            result = predict_sla_for_ticket(ticket.id, session=session)
            risk = result.get("breach_risk_score", 0)
            if risk >= settings.sla_risk_threshold:
                alert = Alert(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    alert_type="sla_breach_risk",
                    message=f"SLA breach risk {risk:.0%} for ticket {ticket.subject[:80]}",
                    severity="warning" if risk < 0.9 else "critical",
                )
                session.add(alert)
                session.commit()
                log_ticket_event(
                    session,
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    action="sla_risk_flagged",
                    actor_type="system",
                    details=result,
                )
                try:
                    from app.services.realtime import broadcast_tenant

                    broadcast_tenant(
                        str(ticket.tenant_id),
                        {"type": "sla_alert", "ticket_id": str(ticket.id), "risk": risk},
                    )
                except Exception:
                    pass
                flagged.append(result)
        return flagged
    finally:
        if owns:
            session.close()
