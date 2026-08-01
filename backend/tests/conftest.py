"""
Pytest fixtures for testing.

Provides:
- test_db: Control-plane database for tests
- test_redis: Redis instance for tests
- mock_vault: MockVaultClient for tests
- test_client: FastAPI TestClient
- redis_for_tests: autouse fixture that reconnects global redis_client per test
"""

import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.models.base import Base
from app.models.tenant import Tenant
from app.models.user import User
from app.models.group import Group, GroupMembership
from app.models.oauth_client import OAuthClient, RefreshToken
from app.models.scope import ScopeRegistry
from app.services.cursor_store import SyncCursor
from app.storage.vault_client import MockVaultClient
from app.storage.redis_client import TenantPartitionedRedisClient

# ---------------------------------------------------------------------------
# DB host auto-detection
# Inside Docker: CONTROL_PLANE_DATABASE_URL contains "@postgres:"
# Locally:       it either isn't set or contains "@localhost:"
# ---------------------------------------------------------------------------
_cp_url = os.getenv("CONTROL_PLANE_DATABASE_URL", "")
if "@postgres:" in _cp_url:
    _db_host = "postgres"
else:
    _db_host = os.getenv("DB_HOST", "localhost")

_redis_url = os.getenv("REDIS_URL", f"redis://{_db_host}:6379")

# Test database URL (reuses control_plane; fixtures drop+recreate tables per test)
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql+asyncpg://postgres:postgres@{_db_host}:5432/control_plane",
)


# ---------------------------------------------------------------------------
# Per-test Redis reconnect  (fixes "Event loop is closed" in pytest-asyncio 0.24)
#
# pytest-asyncio 0.24 creates a NEW event loop for every async test by default.
# A global redis_client._client socket is bound to the PREVIOUS loop, so any
# subsequent test that touches it gets "Future attached to a different loop".
# Solution: disconnect + reconnect the global singleton at the start of every test.
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(autouse=True)
async def redis_for_tests():
    """Reconnect the global redis_client on each test's own event loop.

    pytest-asyncio 0.24 creates a NEW event loop per async test. The global
    redis_client._client socket is bound to the PREVIOUS loop, so we must
    always force-close it and create a brand-new connection on the current loop.
    """
    from app.storage.redis_client import redis_client

    # Force-close any stale connection (regardless of whether _client exists)
    if redis_client._client is not None:
        try:
            await redis_client._client.aclose()
        except Exception:
            pass
    # Always null out _client so connect() creates a fresh one (bypasses guard)
    redis_client._client = None

    # Connect fresh on this test's event loop
    await redis_client.connect()

    yield

    # Flush test keys and disconnect cleanly
    try:
        if redis_client._client:
            await redis_client._client.flushdb()
            await redis_client.disconnect()
    except Exception:
        pass
    redis_client._client = None


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Fixture for test database session.

    Creates a fresh schema for each test (drop_all then create_all).
    Uses NullPool to prevent asyncpg from reusing connections across event loops,
    which causes 'Future attached to a different loop' errors in pytest-asyncio 0.24.
    """
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture
async def test_redis() -> AsyncGenerator[TenantPartitionedRedisClient, None]:
    """
    Fixture for an isolated Redis client on DB 15 (won't clash with the global client).
    """
    redis = TenantPartitionedRedisClient(redis_url=f"redis://{_db_host}:6379/15")
    await redis.connect()

    yield redis

    # Cleanup: flush test DB
    if redis._client:
        await redis._client.flushdb()
    await redis.disconnect()


@pytest_asyncio.fixture
async def mock_vault() -> MockVaultClient:
    """
    Fixture for mock Vault client.
    """
    vault = MockVaultClient()

    # Pre-populate with test secrets
    await vault.set_secret("kv/test-tenant/db_password", "test_password")

    return vault


@pytest.fixture
def test_client() -> TestClient:
    """
    Fixture for FastAPI test client.
    """
    return TestClient(app)
