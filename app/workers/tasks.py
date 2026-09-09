"""Celery task definitions."""

from __future__ import annotations

import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.classify_ticket", bind=True, max_retries=3)
def classify_ticket_task(self, ticket_id: str):
    """Primary async entry after ticket creation — runs full pipeline."""
    try:
        from app.services.pipeline import process_new_ticket

        return process_new_ticket(UUID(ticket_id))
    except Exception as exc:
        logger.exception("classify_ticket_task failed")
        raise self.retry(exc=exc, countdown=5)


@celery_app.task(name="app.workers.tasks.scan_all_sla_risks")
def scan_all_sla_risks():
    from app.services.sla_predictor import scan_sla_risks

    return scan_sla_risks()


def enqueue_ticket_processing(ticket_id: UUID) -> None:
    """Enqueue Celery job; fall back to inline processing if broker unavailable."""
    from app.config import get_settings

    settings = get_settings()
    if settings.app_env != "production":
        from app.services.pipeline import process_new_ticket

        process_new_ticket(ticket_id)
        return
    try:
        classify_ticket_task.delay(str(ticket_id))
    except Exception as exc:
        logger.warning("Celery unavailable (%s); processing inline", exc)
        from app.services.pipeline import process_new_ticket

        process_new_ticket(ticket_id)
