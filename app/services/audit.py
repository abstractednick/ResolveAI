"""Audit + ticket event helpers."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlmodel import Session

from app.models import AuditLog, TicketEvent, utcnow


def log_ticket_event(
    session: Session,
    *,
    tenant_id: UUID,
    ticket_id: UUID,
    action: str,
    actor_type: str = "system",
    actor_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> TicketEvent:
    event = TicketEvent(
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        details=details or {},
        created_at=utcnow(),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def log_audit(
    session: Session,
    *,
    tenant_id: UUID,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    actor_id: Optional[UUID] = None,
    actor_email: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
        created_at=utcnow(),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry
