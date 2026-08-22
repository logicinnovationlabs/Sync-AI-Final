"""
Control-plane database: engine and session management for the tenants table.

This database stores ONLY tenant routing metadata, NEVER tenant content.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.storage.postgres_connect import connect_args_for_url

# Local Docker Postgres needs ssl=False (Windows asyncpg hangs otherwise).
# Hosted Supabase requires TLS even when ENVIRONMENT=development.
_connect_args = connect_args_for_url(settings.control_plane_database_url or "")

# Control-plane engine (for tenants table only)
control_plane_engine: AsyncEngine = create_async_engine(
    settings.control_plane_database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args=_connect_args,
)

# Session factory for control-plane operations
ControlPlaneSessionLocal = async_sessionmaker(
    control_plane_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_control_plane_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI routes that need control-plane DB access.
    
    Yields:
        AsyncSession for the control-plane database.
    """
    async with ControlPlaneSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
