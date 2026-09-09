"""Auto-resolution bot with tool calls for common issues."""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.db import get_session_context
from app.models import Ticket, TicketStatus, utcnow
from app.services.audit import log_ticket_event
from app.services.claude import get_claude

logger = logging.getLogger(__name__)

AUTO_RESOLVABLE = {
    "account_access",
    "password_reset",
    "orders",
    "order_status",
    "billing",
    "subscription",
}


def reset_password(customer_id: str) -> dict[str, Any]:
    """Simulated identity provider password reset."""
    if not customer_id:
        return {"ok": False, "error": "missing_customer_id"}
    return {
        "ok": True,
        "action": "reset_password",
        "customer_id": customer_id,
        "message": f"Password reset link sent for customer {customer_id}",
    }


def get_order_status(order_id: str) -> dict[str, Any]:
    if not order_id:
        return {"ok": False, "error": "missing_order_id"}
    # Deterministic mock status for demo
    statuses = ["processing", "shipped", "delivered", "delayed"]
    status = statuses[sum(ord(c) for c in order_id) % len(statuses)]
    return {
        "ok": True,
        "action": "get_order_status",
        "order_id": order_id,
        "status": status,
        "eta_days": 2 if status != "delivered" else 0,
    }


def check_subscription_status(customer_id: str) -> dict[str, Any]:
    if not customer_id:
        return {"ok": False, "error": "missing_customer_id"}
    return {
        "ok": True,
        "action": "check_subscription_status",
        "customer_id": customer_id,
        "plan": "pro",
        "status": "active",
        "renews_on": "2026-10-01",
    }


TOOLS = {
    "reset_password": reset_password,
    "get_order_status": get_order_status,
    "check_subscription_status": check_subscription_status,
}


def _extract_order_id(text: str) -> str | None:
    match = re.search(r"\b(?:order[#:\s-]*)?([A-Z0-9-]{6,})\b", text, re.I)
    return match.group(1) if match else None


def attempt_auto_resolve(ticket_id: UUID, session: Session | None = None) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return {"resolved": False, "reason": "not_found"}

        category = (ticket.category or "").lower()
        if category not in AUTO_RESOLVABLE and not any(k in category for k in ("password", "order", "subscription", "billing")):
            log_ticket_event(
                session,
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                action="auto_resolve_skipped",
                actor_type="ai",
                details={"reason": "category_not_auto_resolvable", "category": category},
            )
            return {"resolved": False, "reason": "category_not_auto_resolvable"}

        claude = get_claude()
        plan = claude.complete_json(
            system=(
                "You are an auto-resolution agent. Choose one tool if confident: "
                "reset_password, get_order_status, check_subscription_status. "
                "Return JSON: {tool, args, confidence, customer_reply}."
            ),
            user=(
                f"Category: {ticket.category}\nCustomer ID: {ticket.customer_id}\n"
                f"Subject: {ticket.subject}\nBody: {ticket.body}\n"
                f"Tools: {list(TOOLS)}"
            ),
            fallback=None,
        )

        # Heuristic fallback if Claude unavailable
        if not plan:
            text = f"{ticket.subject} {ticket.body}".lower()
            if "password" in text or "login" in text:
                plan = {
                    "tool": "reset_password",
                    "args": {"customer_id": ticket.customer_id or ticket.customer_email},
                    "confidence": 0.8,
                    "customer_reply": "We've sent a password reset link to your email.",
                }
            elif "order" in text:
                order_id = _extract_order_id(f"{ticket.subject} {ticket.body}") or "UNKNOWN"
                plan = {
                    "tool": "get_order_status",
                    "args": {"order_id": order_id},
                    "confidence": 0.75,
                    "customer_reply": None,
                }
            elif "subscription" in text or "billing" in text:
                plan = {
                    "tool": "check_subscription_status",
                    "args": {"customer_id": ticket.customer_id or ticket.customer_email},
                    "confidence": 0.75,
                    "customer_reply": None,
                }
            else:
                return {"resolved": False, "reason": "low_confidence"}

        confidence = float(plan.get("confidence", 0))
        tool_name = plan.get("tool")
        if confidence < 0.7 or tool_name not in TOOLS:
            log_ticket_event(
                session,
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                action="auto_resolve_deferred",
                actor_type="ai",
                details=plan,
            )
            return {"resolved": False, "reason": "low_confidence", "plan": plan}

        args = plan.get("args") or {}
        outcome = TOOLS[tool_name](**args) if args else TOOLS[tool_name]()  # type: ignore[misc]
        log_ticket_event(
            session,
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            action="tool_called",
            actor_type="ai",
            details={"tool": tool_name, "args": args, "outcome": outcome},
        )

        if not outcome.get("ok"):
            return {"resolved": False, "reason": "tool_failed", "outcome": outcome}

        reply = plan.get("customer_reply")
        if not reply:
            reply = (
                f"We've handled your request automatically.\n\n"
                f"Action: {outcome.get('action')}\nResult: {outcome}"
            )

        ticket.status = TicketStatus.resolved
        ticket.auto_resolved = True
        ticket.suggested_reply = reply
        ticket.first_response_sent = True
        ticket.first_responded_at = utcnow()
        ticket.resolved_at = utcnow()
        ticket.updated_at = utcnow()
        session.add(ticket)
        session.commit()

        log_ticket_event(
            session,
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            action="auto_resolved",
            actor_type="ai",
            details={"tool": tool_name, "outcome": outcome, "reply": reply},
        )
        return {"resolved": True, "tool": tool_name, "outcome": outcome, "reply": reply}
    finally:
        if owns:
            session.close()
