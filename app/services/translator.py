"""Multi-language detection and translation."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from app.db import get_session_context
from app.models import Ticket, utcnow
from app.services.audit import log_ticket_event
from app.services.claude import get_claude


def detect_language(text: str) -> str:
    claude = get_claude()
    result = claude.complete_json(
        system="Detect the language of the text. Return JSON: {language: ISO-639-1 code, confidence}.",
        user=text[:2000],
        fallback={"language": "en", "confidence": 0.5},
    )
    lang = str(result.get("language", "en")).lower()[:8]
    return lang or "en"


def translate_incoming(ticket_id: UUID, session: Session | None = None) -> dict:
    owns = session is None
    session = session or get_session_context()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return {"error": "not_found"}

        lang = detect_language(f"{ticket.subject}\n{ticket.body}")
        ticket.language = lang
        if lang != "en":
            claude = get_claude()
            translated = claude.complete(
                system="Translate the following support ticket into clear English. Preserve meaning.",
                user=f"Subject: {ticket.subject}\n\nBody: {ticket.body}",
            )
            ticket.body_original = ticket.body
            # Keep subject; store English body for AI pipelines
            ticket.body = translated
            log_ticket_event(
                session,
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                action="translated_incoming",
                actor_type="ai",
                details={"from": lang, "to": "en"},
            )
        ticket.updated_at = utcnow()
        session.add(ticket)
        session.commit()
        return {"language": lang, "translated": lang != "en"}
    finally:
        if owns:
            session.close()


def translate_outgoing(reply_text: str, target_language: str) -> str:
    if not target_language or target_language == "en":
        return reply_text
    claude = get_claude()
    return claude.complete(
        system=f"Translate this support reply into {target_language}. Keep tone professional and clear.",
        user=reply_text,
    )
