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

# Create Celery app
celery_app = Celery(
    "snyq_backend",
    broker=getattr(settings, "CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=getattr(settings, "CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
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
)

# Test mode: synchronous execution
import os
import sys

task_always_eager = (
    getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
    or os.getenv("CELERY_TASK_ALWAYS_EAGER", "").lower() in ("true", "1")
    or "pytest" in sys.modules
    or "PYTEST_CURRENT_TEST" in os.environ
)
if task_always_eager:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.workers"])
# CeleryInstrumentor is applied in app.core.telemetry.setup_telemetry
