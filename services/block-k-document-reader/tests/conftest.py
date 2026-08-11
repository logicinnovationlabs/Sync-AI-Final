"""Shared pytest fixtures for Block K signoff tests."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure Phase 1 defaults before app imports
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("STORAGE_BACKEND", "mock")
os.environ.setdefault("ACL_BACKEND", "mock")
os.environ.setdefault("ENFORCE_TENANT_ISOLATION", "true")
os.environ.setdefault("STREAM_THRESHOLD_BYTES", str(10 * 1024 * 1024))

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(os.environ.get("FIXTURES_PATH") or (ROOT / "fixtures"))


def make_bearer(
    tenant_id: str,
    principal_id: str = "user-a",
    scopes: list | None = None,
) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "principal_id": principal_id,
                "scopes": scopes or ["document.read"],
            }
        ).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.testsig"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def structured_doc(fixtures_dir: Path) -> Dict[str, Any]:
    path = fixtures_dir / "structured_document.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest_asyncio.fixture
async def k_app():
    """Fresh app stack with in-memory store + mock ACL."""
    # Re-import settings after env defaults
    from app.config import settings
    from app.storage.document_store import InMemoryDocumentStore
    from app.acl.acl_checker import MockACLChecker
    import app.main as main_mod

    store = InMemoryDocumentStore(settings)
    acl = MockACLChecker()
    await store.connect()

    main_mod.store = store
    main_mod.acl_checker = acl

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, store, acl, main_mod.app

    await store.close()
