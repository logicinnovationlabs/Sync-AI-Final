"""Database session helpers for ACL post-check."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def init_db_engine(database_url: Optional[str] = None) -> Optional[AsyncEngine]:
    """Create the async SQLAlchemy engine when ACL backend is postgres."""
    global _engine, _session_factory
    if settings.acl_backend != "postgres":
        logger.info("ACL backend=%s; skipping DB engine init", settings.acl_backend)
        return None

    url = database_url or settings.database_url
    _engine = create_async_engine(
        url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    logger.info("Initialized async DB engine for ACL post-check")
    return _engine


async def close_db_engine() -> None:
    """Dispose the engine on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_db_session():
    """FastAPI dependency: yield a session when postgres ACL is enabled."""
    if _session_factory is None:
        yield None
        return
    async with _session_factory() as session:
        yield session
