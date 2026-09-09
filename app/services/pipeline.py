"""End-to-end ticket processing pipeline after ingestion."""

from __future__ import annotations

import logging
from uuid import UUID

from app.services.auto_resolver import attempt_auto_resolve
from app.services.classifier import analyze_sentiment, classify_ticket
from app.services.csat_predictor import predict_csat
from app.services.dedup import detect_duplicates
from app.services.kb_updater import maybe_draft_kb_from_unresolved
from app.services.reply_assistant import generate_first_response
from app.services.similarity import embed_ticket, find_kb_article, find_similar_tickets
from app.services.sla_predictor import predict_sla_for_ticket
from app.services.summarizer import summarize_thread
from app.services.translator import translate_incoming

logger = logging.getLogger(__name__)


def process_new_ticket(ticket_id: UUID) -> dict:
    """
    Agentic chain:
    translate → classify → sentiment → embed → dedup → similar/KB →
    auto-resolve → first response → SLA → summary → KB updater
    """
    results: dict = {"ticket_id": str(ticket_id)}
    try:
        results["translate"] = translate_incoming(ticket_id)
        results["classify"] = classify_ticket(ticket_id)
        results["sentiment"] = analyze_sentiment(ticket_id)
        results["embed"] = {"dims": len(embed_ticket(ticket_id))}
        results["dedup"] = detect_duplicates(ticket_id)
        if results["dedup"].get("merged") and results["dedup"].get("duplicate_id") == str(ticket_id):
            return results  # this ticket was merged away
        results["similar"] = find_similar_tickets(ticket_id)
        results["kb"] = find_kb_article(ticket_id)
        results["auto_resolve"] = attempt_auto_resolve(ticket_id)
        auto_send = bool(results["auto_resolve"].get("resolved"))
        results["first_response"] = generate_first_response(ticket_id, auto_send=auto_send)
        results["sla"] = predict_sla_for_ticket(ticket_id)
        results["summary"] = summarize_thread(ticket_id)
        if results["auto_resolve"].get("resolved"):
            results["csat"] = predict_csat(ticket_id)
        # Best-effort KB drafting for the tenant
        from app.db import get_session_context
        from app.models import Ticket

        with get_session_context() as session:
            ticket = session.get(Ticket, ticket_id)
            if ticket:
                results["kb_drafts"] = maybe_draft_kb_from_unresolved(ticket.tenant_id, session=session)
        try:
            from app.services.realtime import broadcast_tenant
            from app.db import get_session_context
            from app.models import Ticket

            with get_session_context() as session:
                ticket = session.get(Ticket, ticket_id)
                if ticket:
                    broadcast_tenant(
                        str(ticket.tenant_id),
                        {"type": "ticket_updated", "ticket_id": str(ticket.id), "status": ticket.status.value},
                    )
        except Exception:
            pass
    except Exception as exc:
        logger.exception("process_new_ticket failed for %s", ticket_id)
        results["error"] = str(exc)
    return results
