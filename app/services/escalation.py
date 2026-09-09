"""Escalation routing to specialist teams."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session, select

from app.db import get_session_context
from app.models import Alert, RoutingRule, Ticket, TicketPriority, User, utcnow
from app.services.audit import log_ticket_event


TECH_KEYWORDS = (
    "stacktrace",
    "exception",
    "api error",
    "500",
    "timeout",
    "database",
    "integration",
    "webhook",
    "oauth",
    "sdk",
)


def route_escalation(ticket_id: UUID, session: Session | None = None) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return {"error": "not_found"}

        text = f"{ticket.subject} {ticket.body} {ticket.category or ''}".lower()
        rules = session.exec(
            select(RoutingRule).where(
                RoutingRule.tenant_id == ticket.tenant_id,
                RoutingRule.is_active == True,  # noqa: E712
            )
        ).all()

        matched_rule = None
        for rule in rules:
            if rule.categories and ticket.category in rule.categories:
                matched_rule = rule
                break
            if any(k.lower() in text for k in (rule.keywords or [])):
                matched_rule = rule
                break

        if matched_rule:
            ticket.assigned_team = matched_rule.assign_team
            if matched_rule.priority_override:
                try:
                    ticket.priority = TicketPriority(matched_rule.priority_override)
                except ValueError:
                    pass
            if matched_rule.assign_agent_email:
                agent = session.exec(
                    select(User).where(
                        User.tenant_id == ticket.tenant_id,
                        User.email == matched_rule.assign_agent_email,
                    )
                ).first()
                if agent:
                    ticket.assigned_agent_id = agent.id
        elif any(k in text for k in TECH_KEYWORDS) or ticket.priority == TicketPriority.urgent:
            ticket.assigned_team = ticket.assigned_team or "specialists"
            if ticket.priority != TicketPriority.urgent:
                ticket.priority = TicketPriority.high

        ticket.updated_at = utcnow()
        session.add(ticket)

        alert = Alert(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            alert_type="escalation",
            message=f"Escalated to {ticket.assigned_team}: {ticket.subject[:100]}",
            severity="warning",
        )
        session.add(alert)
        session.commit()

        log_ticket_event(
            session,
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            action="escalated",
            actor_type="ai",
            details={
                "assigned_team": ticket.assigned_team,
                "priority": ticket.priority.value if hasattr(ticket.priority, "value") else ticket.priority,
                "rule": matched_rule.name if matched_rule else None,
            },
        )
        try:
            from app.services.realtime import broadcast_tenant

            broadcast_tenant(
                str(ticket.tenant_id),
                {"type": "escalation", "ticket_id": str(ticket.id), "team": ticket.assigned_team},
            )
        except Exception:
            pass
        return {
            "ticket_id": str(ticket.id),
            "assigned_team": ticket.assigned_team,
            "priority": ticket.priority.value if hasattr(ticket.priority, "value") else str(ticket.priority),
        }
    finally:
        if owns:
            session.close()
