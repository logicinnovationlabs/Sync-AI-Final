"""Block I: Activity Signals Services."""

from app.core.config import settings
from app.services.signals.store import ActivityStore


def get_activity_store() -> ActivityStore:
    """Factory function to get activity store based on configuration."""
    if settings.signals_backend == "postgres":
        from app.services.signals.postgres_store import PostgresActivityStore
        # Use the main database URL for signals
        database_url = settings.database_url or "postgresql://snyq:snyq@localhost:5432/snyq"
        return PostgresActivityStore(database_url)
    else:  # "mock" or default
        from app.services.signals.mock_store import MockActivityStore
        return MockActivityStore()


__all__ = ["ActivityStore", "get_activity_store"]
