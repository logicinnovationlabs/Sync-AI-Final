"""Block L assistant orchestrator — real RS256 JWT + Docker Postgres session store.

Hits the mounted routes on the monolith:
  POST /assistant/orchestrator/chat
  GET  /assistant/orchestrator/sessions/{id}

Episodic memory uses ORCHESTRATOR_DATABASE_URL (conftest points it at
Docker Postgres control_plane).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services.admin.scopes import MEMBER_SCOPES
from app.services.token_service import token_service
from tests.conftest import _get_app

pytestmark = pytest.mark.block_l


@pytest.fixture(autouse=True)
def _offline_chat_provider(monkeypatch):
    """Signoff hits the mounted graph singleton; keep it off the live Qwen path."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "llm_chat_provider", "fake")


TENANT_A = str(uuid4())
TENANT_B = str(uuid4())
USER_ALICE = str(uuid4())
USER_BOB = str(uuid4())


async def _token(tenant_id: str, principal_id: str) -> str:
    return await token_service.issue_access_token(
        tenant_id,
        principal_id,
        MEMBER_SCOPES,
        role="member",
        token_version=0,
    )


@pytest.fixture
def l_client():
    return TestClient(_get_app())


@pytest.mark.asyncio
async def test_l_health(l_client: TestClient):
    resp = l_client.get("/assistant/health")
    assert resp.status_code == 200
    assert resp.json().get("service") == "assistant_orchestrator"


@pytest.mark.asyncio
async def test_l1_chat_requires_matching_tenant(l_client: TestClient):
    token = await _token(TENANT_A, USER_ALICE)
    resp = l_client.post(
        "/assistant/orchestrator/chat",
        json={
            "prompt": "Find documents about Python",
            "session_id": "sess-l1",
            "tenant_id": TENANT_B,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_l2_chat_streams_ndjson(l_client: TestClient):
    token = await _token(TENANT_A, USER_ALICE)
    session_id = f"sess-{uuid4().hex[:8]}"
    resp = l_client.post(
        "/assistant/orchestrator/chat",
        json={"prompt": "Find Python tutorials", "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert "application/x-ndjson" in (resp.headers.get("content-type") or "")
    body = resp.text.strip()
    assert body, "expected streamed NDJSON"
    assert '"type"' in body


@pytest.mark.asyncio
async def test_l3_cross_tenant_session_denied(l_client: TestClient):
    token_a = await _token(TENANT_A, USER_ALICE)
    session_id = f"sess-{uuid4().hex[:8]}"
    chat = l_client.post(
        "/assistant/orchestrator/chat",
        json={"prompt": "hello", "session_id": session_id},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert chat.status_code == 200, chat.text

    token_b = await _token(TENANT_B, USER_BOB)
    stolen = l_client.get(
        f"/assistant/orchestrator/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert stolen.status_code in (403, 404)


@pytest.mark.asyncio
async def test_l4_chat_persists_session_in_docker_postgres(l_client: TestClient):
    """Round-trip session memory through Docker Postgres (control_plane)."""
    from app.services.assistant.infrastructure.memory_store import EpisodicMemoryStore

    token = await _token(TENANT_A, USER_ALICE)
    session_id = f"sess-{uuid4().hex[:8]}"
    resp = l_client.post(
        "/assistant/orchestrator/chat",
        json={"prompt": "remember this session", "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    store = EpisodicMemoryStore()
    store.ensure_schema()
    loaded = store.load_session(TENANT_A, session_id)
    assert loaded is not None
    assert loaded.session_id == session_id
    assert loaded.tenant_id == TENANT_A


@pytest.mark.asyncio
async def test_l_empty_prompt_rejected(l_client: TestClient):
    token = await _token(TENANT_A, USER_ALICE)
    resp = l_client.post(
        "/assistant/orchestrator/chat",
        json={"prompt": "", "session_id": "sess-empty"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
