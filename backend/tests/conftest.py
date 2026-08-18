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

from app.models.base import Base
from app.models.tenant import Tenant
from app.models.user import User
from app.models.group import Group, GroupMembership
from app.models.oauth_client import OAuthClient, RefreshToken
from app.models.scope import ScopeRegistry
from app.models.audit_log import AuditLog  # noqa: F401 — Block N metadata
from app.models.tenant_connector import TenantConnector  # noqa: F401
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

# Block L episodic memory: same Docker Postgres as control_plane (not :5433)
os.environ.setdefault(
    "ORCHESTRATOR_DATABASE_URL",
    f"postgresql://postgres:postgres@{_db_host}:5432/control_plane",
)

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


def _get_app():
    """Lazy-import FastAPI app so Block D–J tests do not need Block L (langgraph)."""
    from app.main import app
    return app


@pytest.fixture
def test_client() -> TestClient:
    """
    Fixture for FastAPI test client.
    """
    return TestClient(_get_app())


# Block D verify compose (FIX_PASS_D-E-G Phase 2): host ports only.
_K_PHASE2_PG_DSN = "postgresql+asyncpg://postgres:verify@localhost:5435/block_d_verify"
_K_PHASE2_MINIO_ENDPOINT = "localhost:9000"
_K_PHASE2_MINIO_ACCESS = "minioadmin"
_K_PHASE2_MINIO_SECRET = "minioadmin"
_K_PHASE2_BUCKET = "documents"


async def _k_phase2_store(settings):
    """Construct MinioDocumentStore against Block D verify Postgres+MinIO.

    Raises if the factory still returns the in-memory double.
    """
    from pathlib import Path
    import json as _json
    from app.services.document_reader.store import (
        MinioDocumentStore,
        create_document_store,
    )

    saved = {
        "storage_backend": settings.storage_backend,
        "storage_endpoint": settings.storage_endpoint,
        "storage_access_key": settings.storage_access_key,
        "storage_secret_key": settings.storage_secret_key,
        "storage_bucket": settings.storage_bucket,
        "storage_secure": settings.storage_secure,
        "control_plane_database_url": settings.control_plane_database_url,
    }
    settings.storage_backend = "minio"
    settings.storage_endpoint = _K_PHASE2_MINIO_ENDPOINT
    settings.storage_access_key = _K_PHASE2_MINIO_ACCESS
    settings.storage_secret_key = _K_PHASE2_MINIO_SECRET
    settings.storage_bucket = _K_PHASE2_BUCKET
    settings.storage_secure = False
    settings.control_plane_database_url = _K_PHASE2_PG_DSN

    store = create_document_store(settings)
    if not isinstance(store, MinioDocumentStore):
        raise RuntimeError(
            f"K Phase 2 fixture expected MinioDocumentStore, got {type(store).__name__}"
        )
    await store.connect()

    async with store.db_pool.acquire() as conn:
        n_before = await conn.fetchval("SELECT COUNT(*) FROM documents")
    print(
        f"[BLOCK K] Phase 2 store={type(store).__name__} "
        f"minio={_K_PHASE2_MINIO_ENDPOINT} pg=localhost:5435/block_d_verify "
        f"rows_before_seed={n_before}"
    )

    if int(n_before or 0) == 0:
        z_path = Path(__file__).parent / "fixtures" / "block_z" / "corpus_docs.json"
        if z_path.exists():
            z_data = _json.loads(z_path.read_text(encoding="utf-8"))
            for doc in z_data.get("documents") or []:
                await store.upsert(
                    str(doc.get("tenant_id") or "tenant_f_test"),
                    str(doc["document_id"]),
                    title=str(doc.get("title") or ""),
                    body=str(doc.get("body_text") or ""),
                    owner_principal_id=str(doc.get("owner") or ""),
                    structured_metadata={
                        "language": doc.get("language"),
                        "tags": doc.get("tags") or [],
                    },
                    created_at=doc.get("updated_at"),
                    updated_at=doc.get("updated_at"),
                )
            async with store.db_pool.acquire() as conn:
                n_after = await conn.fetchval("SELECT COUNT(*) FROM documents")
            print(f"[BLOCK K] seeded Block Z corpus; rows_after_seed={n_after}")

    return store, saved


def _k_restore_settings(settings, saved: dict) -> None:
    for key, value in saved.items():
        setattr(settings, key, value)
@pytest_asyncio.fixture
async def k_app():
    """
    Fixture for Block K (Document Reader) tests — Phase 2.

    Document store is MinIO + Block D verify Postgres (not InMemoryDocumentStore).
    ACL remains MockACLChecker so K1 can grant/revoke/count (Block C is out of scope).
    """
    from httpx import ASGITransport, AsyncClient
    from app.core.config import settings
    from app.services.document_reader.acl_checker import MockACLChecker

    store, saved = await _k_phase2_store(settings)
    acl = MockACLChecker()

    fastapi_app = _get_app()

    import app.api.v1.document as doc_module
    original_store = doc_module.store
    original_acl = doc_module.acl_checker

    doc_module.store = store
    doc_module.acl_checker = acl

    transport = ASGITransport(app=fastapi_app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, store, acl, fastapi_app
    finally:
        doc_module.store = original_store
        doc_module.acl_checker = original_acl
        await store.close()
        _k_restore_settings(settings, saved)


@pytest_asyncio.fixture
async def k_app_async():
    """Async fixture for Block K — same Phase 2 store as k_app."""
    from httpx import AsyncClient
    from app.core.config import settings
    from app.services.document_reader.acl_checker import MockACLChecker

    store, saved = await _k_phase2_store(settings)
    acl = MockACLChecker()

    import app.api.v1.document as doc_module
    original_store = doc_module.store
    original_acl = doc_module.acl_checker

    doc_module.store = store
    doc_module.acl_checker = acl

    fastapi_app = _get_app()
    try:
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            yield client, store, acl, fastapi_app
    finally:
        doc_module.store = original_store
        doc_module.acl_checker = original_acl
        await store.close()
        _k_restore_settings(settings, saved)


# ---------------------------------------------------------------------------
# Block L: Assistant Orchestrator Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def l_app():
    """
    Fixture for Block L (Assistant Orchestrator) tests.
    
    Returns TestClient configured for assistant endpoints.
    """
    return TestClient(_get_app())


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def make_bearer(tenant_id: str, principal_id: str, scopes: list = None) -> str:
    """Issue a test JWT that matches TokenService (RS256 + same key material).

    The previous HS256 HMAC helper was rejected by validate_token
    (`algorithms=[settings.jwt_algorithm]`, default RS256).
    """
    import jwt
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from app.services.token_service import token_service

    if scopes is None:
        scopes = ["read", "write"]

    token_service._load_keys()
    now = datetime.now(timezone.utc)
    payload = {
        "iss": token_service.issuer,
        "sub": principal_id,
        "principal_id": principal_id,
        "tenant_id": tenant_id,
        "scopes": scopes,
        "iat": now,
        "exp": now + timedelta(hours=1),
        "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        token_service._private_key,
        algorithm=token_service.algorithm,
        headers={"kid": token_service._active_kid},
    )
