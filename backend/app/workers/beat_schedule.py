"""
Celery Beat schedule - periodic tasks.

Schedules:
- renew_watch_channels: Run every N hours to renew expiring watches
- run_scheduled_tenant_backups: Daily tenant schema backups
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
    "scheduled-tenant-backups": {
        "task": "app.workers.tasks.run_scheduled_tenant_backups",
        "schedule": crontab(hour=2, minute=0),
        "options": {
            "expires": 7200,
        },
    },
}

# Timezone
celery_app.conf.timezone = "UTC"
