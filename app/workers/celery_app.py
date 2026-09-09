"""Celery app and async ticket jobs."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "resolveai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_always_eager=settings.app_env != "production",
    task_eager_propagates=True,
    beat_schedule={
        "sla-scan-every-15-min": {
            "task": "app.workers.tasks.scan_all_sla_risks",
            "schedule": 15 * 60,
        },
    },
)
