"""
Celery Application Factory
Configures Celery with Redis broker and result backend.
"""
from __future__ import annotations

from celery import Celery

from ...application.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "ventro",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["src.infrastructure.jobs.reconciliation_tasks"],
    )
    app.conf.update(
        # Serialization
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],

        # Reliability
        task_acks_late=True,                  # Ack only after task completes (not before)
        task_reject_on_worker_lost=True,      # Re-queue if worker dies mid-task
        task_track_started=True,              # Allow querying "STARTED" state

        # Timeouts
        task_soft_time_limit=300,             # 5 minutes: raises SoftTimeLimitExceeded
        task_time_limit=360,                  # 6 minutes: kills worker after this

        # Concurrency
        worker_prefetch_multiplier=1,         # Don't pre-fetch; ensures fair load distribution
        worker_max_tasks_per_child=100,       # Restart worker after 100 tasks to prevent memory leaks

        # Result expiry
        result_expires=3600,                  # Keep results for 1 hour
        result_persistent=True,

        # Routing
        task_routes={
            "reconciliation.*": {"queue": "reconciliation"},
            "celery.*": {"queue": "celery"},
        },

        # Beat schedule (if needed for periodic tasks)
        beat_schedule={},
    )
    return app


celery_app = create_celery_app()
