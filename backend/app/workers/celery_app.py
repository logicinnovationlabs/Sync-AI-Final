"""
Celery application configuration.

Broker: Redis
Backend: Redis
Task always eager: Configurable (true in tests for synchronous execution)
"""

import app.core.compat  # noqa: F401 — pkg_resources shim before OpenTelemetry
from celery import Celery
from app.core.config import settings
from app.core.telemetry import setup_telemetry

setup_telemetry(service_name="snyq-celery")


def _celery_redis_url(explicit: str | None) -> str:
    """Prefer CELERY_* then the shared Redis URL so host and Docker both enqueue."""
    if explicit:
        return explicit
    return getattr(settings, "session_store_redis_url", None) or "redis://localhost:6379/1"


# Create Celery app
celery_app = Celery(
    "snyq_backend",
    broker=_celery_redis_url(getattr(settings, "celery_broker_url", None)),
    backend=_celery_redis_url(getattr(settings, "celery_result_backend", None)),
)

# Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3000,  # 50 minutes soft limit
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.backfill_tenant_source": {"queue": "google"},
        "app.workers.tasks.backfill_source": {"queue": "google"},
        "app.workers.tasks.process_drive_notification": {"queue": "google"},
        "app.workers.tasks.process_gmail_notification": {"queue": "google"},
        "app.workers.tasks.renew_watch_channels": {"queue": "google"},
        "app.workers.tasks.google_queue_ping": {"queue": "google"},
    },
)

# Test mode: synchronous execution
import os
import sys

task_always_eager = (
    getattr(settings, "celery_task_always_eager", False)
    or os.getenv("CELERY_TASK_ALWAYS_EAGER", "").lower() in ("true", "1")
    or "pytest" in sys.modules
    or "PYTEST_CURRENT_TEST" in os.environ
)
if task_always_eager:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.workers"])
import app.workers.tasks  # noqa: F401, E402 — register backfill_source on the google queue
# CeleryInstrumentor is applied in app.core.telemetry.setup_telemetry

# Register periodic tasks (watch renewal, scheduled backups)
import app.workers.beat_schedule  # noqa: F401, E402
