"""Store factory - mock (Phase 1) or postgres (Phase 2)."""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.services.activity_store import ActivityStore
from app.services.mock_store import MockActivityStore

logger = logging.getLogger(__name__)

_mock_singleton: Optional[MockActivityStore] = None
_pg_singleton: Optional[ActivityStore] = None


def reset_mock_store() -> MockActivityStore:
    """Replace the mock singleton (used by tests)."""
    global _mock_singleton
    _mock_singleton = MockActivityStore()
    return _mock_singleton


def get_activity_store(backend: Optional[str] = None) -> ActivityStore:
    """Return the configured activity store."""
    global _mock_singleton, _pg_singleton
    chosen = (backend or settings.signals_backend or "mock").lower()

    if chosen == "postgres":
        if _pg_singleton is None:
            from app.services.postgres_store import PostgresActivityStore

            _pg_singleton = PostgresActivityStore(settings.database_url)
            logger.info("Using PostgresActivityStore")
        return _pg_singleton

    if _mock_singleton is None:
        _mock_singleton = MockActivityStore()
        logger.info("Using MockActivityStore")
    return _mock_singleton
