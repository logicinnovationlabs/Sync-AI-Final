"""Shared pytest fixtures for Block I signoff tests."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SIGNALS_BACKEND", os.environ.get("SIGNALS_BACKEND", "mock"))
os.environ.setdefault("ENFORCE_TENANT_ISOLATION", "true")
os.environ.setdefault("CACHE_ENABLED", "true")

_FIXTURES_ENV = os.environ.get("FIXTURES_PATH")
FIXTURES = Path(_FIXTURES_ENV) if _FIXTURES_ENV else (ROOT / "fixtures")


def _load_json(name: str) -> Dict[str, Any]:
    path = FIXTURES / name
    if not path.exists():
        # Auto-generate if missing
        from fixtures.generate_fixtures import main as gen

        gen()
    return json.loads(path.read_text(encoding="utf-8"))


def make_bearer(
    tenant_id: str,
    principal_id: str = "p-user-001",
    scopes=None,
) -> str:
    if scopes is None:
        scopes = ["activity.ingest", "signals.read", "signals.admin"]
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "principal_id": principal_id,
                "sub": principal_id,
                "scopes": scopes,
            }
        ).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.testsig"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def events_fixture() -> Dict[str, Any]:
    return _load_json("events.json")


@pytest.fixture(scope="session")
def privacy_cases() -> Dict[str, Any]:
    return _load_json("privacy_test_cases.json")


@pytest.fixture(scope="session")
def retention_cases() -> Dict[str, Any]:
    return _load_json("retention_test_cases.json")


@pytest.fixture(scope="session")
def ground_truth() -> Dict[str, Any]:
    return _load_json("signal_ground_truth.json")


@pytest.fixture(scope="session")
def backend() -> str:
    return os.environ.get("SIGNALS_BACKEND", "mock").lower()


@pytest.fixture
async def store(backend):
    if backend == "postgres":
        from app.services.factory import get_activity_store

        s = get_activity_store("postgres")
        # Isolate test tenants
        for t in ("tenant-a", "tenant-b", "tenant-c", "tenant-iso-a", "tenant-iso-b"):
            await s.clear_tenant(t)
        return s

    from app.services.factory import reset_mock_store

    return reset_mock_store()


@pytest.fixture
async def client(store, backend):
    """ASGI test client bound to a fresh store."""
    # Ensure factory returns our store
    import app.services.factory as factory

    if backend == "mock":
        factory._mock_singleton = store
    else:
        factory._pg_singleton = store

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def auth_headers(tenant_id: str, principal_id: str = "p-user-001", scopes=None) -> Dict[str, str]:
    return {"Authorization": f"Bearer {make_bearer(tenant_id, principal_id, scopes)}"}
