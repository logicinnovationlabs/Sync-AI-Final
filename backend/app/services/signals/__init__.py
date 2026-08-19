"""Block I: Activity Signals Services."""

from app.core.backends import mock_backends_allowed, refuse_mock_backend
from app.core.config import settings
from app.services.signals.store import ActivityStore

_mock_instance = None
_postgres_instance = None


def get_activity_store() -> ActivityStore:
    """Process-level activity store. Mock is a singleton so ingest and query share state."""
    global _mock_instance, _postgres_instance
    backend = (settings.signals_backend or "mock").strip().lower()
    if backend == "postgres":
        from app.services.signals.postgres_store import PostgresActivityStore

        if _postgres_instance is None:
            database_url = (
                getattr(settings, "database_url", None)
                or settings.control_plane_database_url
                or "postgresql://snyq:snyq@localhost:5432/snyq"
            )
            if str(database_url).startswith("postgresql+asyncpg://"):
                database_url = str(database_url).replace(
                    "postgresql+asyncpg://", "postgresql://", 1
                )
            _postgres_instance = PostgresActivityStore(database_url)
        return _postgres_instance

    refuse_mock_backend("SIGNALS_BACKEND", backend, "postgres")
    if not mock_backends_allowed():
        raise RuntimeError("SIGNALS_BACKEND=mock is not allowed outside development/test")
    if _mock_instance is None:
        from app.services.signals.mock_store import MockActivityStore

        _mock_instance = MockActivityStore()
    return _mock_instance


__all__ = ["ActivityStore", "get_activity_store"]
