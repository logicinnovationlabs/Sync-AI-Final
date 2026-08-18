"""Block M MCP gateway — M1–M4 against real control_plane Postgres + Redis."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.audit_log import AuditLog
from app.models.tool_policy import ToolPolicy
from app.services.mcp_gateway.audit import ACTION_TYPE
from app.services.mcp_gateway.revocation import mcp_session_cache
from app.services.revocation import revocation_service
from app.services.token_service import token_service
from tests.conftest import TEST_DB_URL, _get_app, make_bearer

pytestmark = pytest.mark.block_m

# Clearly test data — never a production tenant slug.
TENANT = "mcp-m-test-tenant"
SERVER = "default"
USER = str(uuid4())
SA_CLIENT = "sa-client-mcp-m-test"
VICTIM = str(uuid4())


async def _session_factory():
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


@pytest_asyncio.fixture
async def m_seed(monkeypatch):
    """Seed allowlist rows on control_plane; patch MCP DB factory to TEST_DB_URL."""
    from app.storage import control_plane_db
    from app.services.mcp_gateway import audit as mcp_audit

    engine, factory = await _session_factory()
    monkeypatch.setattr(control_plane_db, "ControlPlaneSessionLocal", factory)
    monkeypatch.setattr(mcp_audit, "ControlPlaneSessionLocal", factory)

    async with factory() as session:
        await session.execute(delete(ToolPolicy).where(ToolPolicy.tenant_id == TENANT))
        await session.execute(delete(AuditLog).where(AuditLog.tenant_id == TENANT))
        session.add_all(
            [
                ToolPolicy(
                    tenant_id=TENANT,
                    server_name=SERVER,
                    tool_name="search",
                    allowed=True,
                ),
                ToolPolicy(
                    tenant_id=TENANT,
                    server_name=SERVER,
                    tool_name="read_document",
                    allowed=True,
                ),
                ToolPolicy(
                    tenant_id=TENANT,
                    server_name=SERVER,
                    tool_name="not_allowlisted_tool",
                    allowed=False,
                ),
            ]
        )
        await session.commit()

    mcp_session_cache._entries.clear()
    mcp_session_cache._revoked_jtis.clear()
    mcp_session_cache._revoked_principals.clear()

    yield factory

    async with factory() as session:
        await session.execute(delete(ToolPolicy).where(ToolPolicy.tenant_id == TENANT))
        await session.execute(delete(AuditLog).where(AuditLog.tenant_id == TENANT))
        await session.commit()
    await engine.dispose()


def _headers(principal: str = USER, tenant: str = TENANT) -> dict:
    return {
        "Authorization": f"Bearer {make_bearer(tenant, principal, scopes=['search.read', 'document.read'])}",
        "X-MCP-Client": "block-m-pytest",
    }


@pytest.mark.asyncio
async def test_m1_no_service_account_escalation(m_seed):
    """M1: 20 impersonation attempts via a service-account token — 0 successes."""
    with TestClient(_get_app()) as client:
        rejected = 0
        for i in range(20):
            resp = client.post(
                f"/mcp/{SERVER}",
                headers=_headers(SA_CLIENT),
                json={
                    "tool": "search",
                    "user_id": VICTIM,
                    "arguments": {"query": f"escalation-{i}", "user_id": VICTIM},
                },
            )
            assert resp.status_code == 403, resp.text
            rejected += 1
        assert rejected == 20


@pytest.mark.asyncio
async def test_m2_non_allowlisted_tool_rejected(m_seed):
    """M2: non-allowlisted tool on a persona endpoint is 100% rejected."""
    with TestClient(_get_app()) as client:
        resp = client.post(
            f"/mcp/{SERVER}",
            headers=_headers(),
            json={"tool": "not_allowlisted_tool", "arguments": {"query": "x"}},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Tool not allowlisted"

        missing = client.post(
            f"/mcp/{SERVER}",
            headers=_headers(),
            json={"tool": "definitely_missing_tool", "arguments": {}},
        )
        assert missing.status_code == 403


@pytest.mark.asyncio
async def test_m3_audit_completeness_20_calls(m_seed):
    """M3: 20 tool calls each produce host, client, user, tool, outcome."""
    with TestClient(_get_app()) as client:
        for i in range(10):
            resp = client.post(
                f"/mcp/{SERVER}",
                headers=_headers(),
                json={"tool": "search", "arguments": {"query": f"m3-search-{i}"}},
            )
            assert resp.status_code == 200, resp.text
        for i in range(10):
            resp = client.post(
                f"/mcp/{SERVER}",
                headers=_headers(),
                json={"tool": "not_allowlisted_tool", "arguments": {"query": f"m3-deny-{i}"}},
            )
            assert resp.status_code == 403, resp.text

    factory = m_seed
    async with factory() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.tenant_id == TENANT).where(
                    AuditLog.action_type == ACTION_TYPE
                )
            )
        ).scalars().all()
        assert len(rows) >= 20, f"expected >=20 audit rows, got {len(rows)}"
        complete = 0
        for row in rows:
            target = row.target_json or {}
            if all(k in target for k in ("host", "client", "user", "tool", "outcome")):
                complete += 1
        sampled = rows[:20]
        assert all(
            all(k in (r.target_json or {}) for k in ("host", "client", "user", "tool", "outcome"))
            for r in sampled
        )
        assert complete >= 20


@pytest.mark.asyncio
async def test_m4_revoke_invalidates_within_60s(m_seed):
    """M4: Block A revoke_token → next MCP call is 401 within 60s."""
    token = make_bearer(TENANT, USER, scopes=["search.read"])
    headers = {"Authorization": f"Bearer {token}", "X-MCP-Client": "block-m-pytest"}
    with TestClient(_get_app()) as client:
        first = client.post(
            f"/mcp/{SERVER}",
            headers=headers,
            json={"tool": "search", "arguments": {"query": "m4-before-revoke"}},
        )
        assert first.status_code == 200, first.text

        started = time.perf_counter()
        factory = m_seed
        async with factory() as session:
            await revocation_service.revoke_token(token, TENANT, session)
        decoded = await token_service.decode_without_validation(token)
        mcp_session_cache.apply_event(
            {
                "event_type": "token_revoked",
                "tenant_id": TENANT,
                "jti": decoded.get("jti"),
            }
        )
        second = client.post(
            f"/mcp/{SERVER}",
            headers=headers,
            json={"tool": "search", "arguments": {"query": "m4-after-revoke"}},
        )
        elapsed = time.perf_counter() - started
        assert second.status_code == 401, second.text
        assert elapsed <= 60.0, f"revocation took {elapsed:.3f}s"
