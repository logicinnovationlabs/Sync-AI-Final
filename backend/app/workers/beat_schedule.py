"""
Celery Beat schedule - periodic tasks.

Schedules:
- renew_watch_channels: Run every N hours to renew expiring watches
"""

from celery.schedules import crontab
from app.workers.celery_app import celery_app
from app.core.config import settings

# Get renewal check interval from settings (default: 24 hours)
RENEWAL_CHECK_HOURS = getattr(settings, "WATCH_RENEWAL_CHECK_HOURS", 24)

# Configure Beat schedule
celery_app.conf.beat_schedule = {
    "renew-watch-channels": {
        "task": "app.workers.tasks.renew_watch_channels",
        "schedule": RENEWAL_CHECK_HOURS * 3600.0,  # Convert hours to seconds
        "options": {
            "expires": 3600,  # Task expires after 1 hour if not picked up
        },
    },
}

# Timezone
celery_app.conf.timezone = "UTC"
