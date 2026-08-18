"""Block N signoff (N1, N2, N3) against real Postgres + Redis via the admin HTTP surface."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text

from app.api.deps import get_tenant, get_tenant_session
from app.core.exceptions import RevokedTokenError
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.models.tenant_connector import TenantConnector
from app.models.user import User
from app.services.admin.scopes import scopes_for_role
from app.services.native_auth import native_auth_service
from app.services.tenant_resolver import TenantRouting, tenant_resolver
from app.services.token_service import token_service
from app.storage.vault_client import vault_client
from tests.conftest import TEST_DB_URL


# Distinct action types the real /admin/* routes persist (tenant bootstrap
# POST /admin/tenants does not call write_audit_log — not used here).
N1_ACTION_TYPES = (
    "user.created",
    "user.updated",
    "user.password_reset",
    "user.deactivated",
    "connector.enabled",
    "connector.updated",
    "connector.removed",
    "session.revoked",
)

# Same floor the original N2 suite declared as representative; 90-day span is new.
N2_VOLUME = 100_000
N2_WINDOW_DAYS = 90
N2_QUERY_COUNT = 100  # F1 / G3 / J1 p95 sample size


async def create_tenant_and_admin(test_db) -> tuple[Tenant, User, str]:
    """Create a tenant + admin via services, returning (tenant, admin_user, admin_jwt)."""
    tenant_id = uuid4()
    db_secret_key = f"kv/tenant-{tenant_id}/db_password"
    await vault_client.set_secret(db_secret_key, "testpass")
    tenant = Tenant(
        tenant_id=tenant_id,
        name="TestOrg",
        subdomain=f"test-{uuid4().hex[:8]}",
        tenancy_mode="isolated_db",
        config={},
        db_host="localhost",
        db_name="control_plane",
        db_user="postgres",
        db_secret_key=db_secret_key,
    )
    test_db.add(tenant)
    await test_db.commit()
    await test_db.refresh(tenant)

    admin = await native_auth_service.create_native_user(
        email=f"admin@{tenant.subdomain}.com",
        password="SecurePass123!",
        display_name="Admin",
        tenant_id=tenant_id,
        db_session=test_db,
        role="admin",
        must_change_password=False,
        is_active=True,
    )

    token = await token_service.issue_access_token(
        str(tenant_id),
        str(admin.principal_id),
        scopes_for_role("admin"),
        role="admin",
        token_version=0,
    )
    return tenant, admin, token


@pytest.fixture(scope="function")
async def test_tenant_and_admin(test_db):
    """Fresh tenant + admin per test. Cleanup uses str() for VARCHAR audit_logs.tenant_id."""
    tenant, admin, token = await create_tenant_and_admin(test_db)
    tenant_id_str = str(tenant.tenant_id)
    tenant_pk = tenant.tenant_id
    yield tenant, admin, token

    try:
        await test_db.rollback()
    except Exception:
        pass
    await test_db.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant_id_str))
    await test_db.execute(
        delete(TenantConnector).where(TenantConnector.tenant_id == tenant_pk)
    )
    await test_db.execute(delete(User).where(User.tenant_id == tenant_pk))
    await test_db.execute(delete(Tenant).where(Tenant.tenant_id == tenant_pk))
    await test_db.commit()


@pytest.fixture(scope="function")
async def n_client(test_db, test_tenant_and_admin, monkeypatch):
    """HTTP client against the real admin route handlers on real Postgres.

    Mounts ``admin_router`` on a slim FastAPI app so httpx ASGITransport does
    not deadlock on ``TenantMiddleware`` (Starlette BaseHTTPMiddleware). Route
    functions in ``app.api.v1.admin.*`` are unchanged. get_tenant_session uses
    a separate NullPool session. Auth still uses token_service.validate_token.
    """
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.api.v1.admin import admin_router
    from app.connectors.org import router as connectors_org_router

    tenant, admin, token = test_tenant_and_admin
    routing = TenantRouting(
        tenant_id=str(tenant.tenant_id),
        db_host="localhost",
        db_name="unused",
        db_user="unused",
        db_password="unused",
        config={},
    )

    async def fake_resolve(tenant_id: str) -> TenantRouting:
        return routing

    monkeypatch.setattr(tenant_resolver, "resolve", fake_resolve)

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_tenant() -> TenantRouting:
        return routing

    async def override_session():
        async with Session() as session:
            yield session

    app = FastAPI()
    app.include_router(admin_router)
    app.include_router(connectors_org_router)
    app.dependency_overrides[get_tenant] = override_tenant
    app.dependency_overrides[get_tenant_session] = override_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, tenant, admin, token
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _admin(client: AsyncClient, token: str, method: str, path: str, **kwargs):
    response = await client.request(method, path, headers=_auth(token), **kwargs)
    assert response.status_code < 400, (
        f"{method} {path} -> {response.status_code} {response.text}"
    )
    return response


async def _matching_audit_count(test_db, tenant_id, action_type: str, needle: str) -> int:
    result = await test_db.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == str(tenant_id))
        .where(AuditLog.action_type == action_type)
    )
    rows = result.scalars().all()
    return sum(1 for row in rows if needle in str(row.target_json or {}))


# ---------- N1: Audit Completeness ----------

@pytest.mark.asyncio
async def test_n1_audit_completeness(test_db, n_client):
    """N1: 20 distinct admin HTTP actions; 100% must produce matching audit rows."""
    client, tenant, _admin_user, token = n_client
    tid = tenant.tenant_id
    performed: list[tuple[str, str]] = []

    created_ids: list[str] = []
    for i in range(5):
        body = {
            "email": f"user{i}@{tenant.subdomain}.com",
            "display_name": f"User {i}",
            "role": "member",
        }
        resp = await _admin(client, token, "POST", "/admin/users", json=body)
        pid = resp.json()["principal_id"]
        created_ids.append(pid)
        performed.append(("user.created", pid))
        assert await _matching_audit_count(test_db, tid, "user.created", pid) >= 1

    await _admin(
        client, token, "PATCH", f"/admin/users/{created_ids[0]}", json={"role": "admin"}
    )
    performed.append(("user.updated", created_ids[0]))
    assert await _matching_audit_count(test_db, tid, "user.updated", created_ids[0]) >= 1

    await _admin(
        client,
        token,
        "PATCH",
        f"/admin/users/{created_ids[1]}",
        json={"is_active": True},
    )
    performed.append(("user.updated", created_ids[1]))
    assert await _matching_audit_count(test_db, tid, "user.updated", created_ids[1]) >= 1

    for pid in created_ids[2:4]:
        await _admin(client, token, "POST", f"/admin/users/{pid}/reset-password")
        performed.append(("user.password_reset", pid))
        assert await _matching_audit_count(test_db, tid, "user.password_reset", pid) >= 1

    for source in ("gmail", "drive", "slack"):
        await _admin(
            client,
            token,
            "POST",
            "/connectors",
            json={"source_type": source, "enabled": True, "config": {"n1": True}},
        )
        performed.append(("connector.enabled", source))
        assert await _matching_audit_count(test_db, tid, "connector.enabled", source) >= 1

    await _admin(
        client,
        token,
        "POST",
        "/connectors",
        json={"source_type": "gmail", "enabled": False, "config": {"n1": "updated"}},
    )
    performed.append(("connector.updated", "gmail"))
    assert await _matching_audit_count(test_db, tid, "connector.updated", "gmail") >= 1

    await _admin(
        client,
        token,
        "POST",
        "/connectors",
        json={"source_type": "drive", "enabled": True, "config": {"n1": "updated"}},
    )
    performed.append(("connector.updated", "drive"))
    assert await _matching_audit_count(test_db, tid, "connector.updated", "drive") >= 1

    for source in ("slack", "drive"):
        await _admin(client, token, "DELETE", f"/connectors/{source}")
        performed.append(("connector.removed", source))
        assert await _matching_audit_count(test_db, tid, "connector.removed", source) >= 1

    for pid in created_ids[0:2]:
        await _admin(client, token, "DELETE", f"/admin/users/{pid}")
        performed.append(("user.deactivated", pid))
        assert await _matching_audit_count(test_db, tid, "user.deactivated", pid) >= 1

    for pid in created_ids[2:4]:
        await _admin(
            client, token, "POST", "/admin/sessions/revoke", json={"user_id": pid}
        )
        performed.append(("session.revoked", pid))
        assert await _matching_audit_count(test_db, tid, "session.revoked", pid) >= 1

    assert len(performed) == 20, f"expected 20 distinct actions, got {len(performed)}"
    types_used = {action for action, _ in performed}
    missing_types = set(N1_ACTION_TYPES) - types_used
    assert not missing_types, f"did not exercise action types: {missing_types}"

    total = (
        await test_db.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.tenant_id == str(tid))
        )
    ).scalar_one()
    print(
        f"N1 actions={len(performed)} types={sorted(types_used)} "
        f"audit_rows={int(total)} missing_audit=0"
    )
    assert int(total) >= 20


# ---------- N2: Search Latency (p95 ≤ 5s) ----------

@pytest.mark.asyncio
async def test_n2_audit_latency(test_db, n_client):
    """N2: GET /admin/audit over a 90-day window on 100k rows; p95 ≤5s."""
    client, tenant, admin, token = n_client
    actor_id = admin.principal_id

    await test_db.execute(
        text(
            "INSERT INTO audit_logs (id, tenant_id, actor_id, action_type, target_json, ip_address, created_at) "
            "SELECT gen_random_uuid(), CAST(:tenant_id AS varchar), CAST(:actor_id AS uuid), 'test.bulk', "
            "jsonb_build_object('idx', idx), '127.0.0.1', "
            "NOW() - ((idx::numeric / :volume) * interval '90 days') "
            "FROM generate_series(1, :volume) AS idx"
        ),
        {
            "tenant_id": str(tenant.tenant_id),
            "actor_id": str(actor_id),
            "volume": N2_VOLUME,
        },
    )
    await test_db.commit()

    now = datetime.now(timezone.utc)
    # 1h pad vs Postgres NOW() so the idx=volume boundary row stays inside the window.
    date_from = (now - timedelta(days=N2_WINDOW_DAYS, hours=1)).isoformat()
    date_to = (now + timedelta(hours=1)).isoformat()
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "page": 1,
        "page_size": 50,
    }

    latencies_ms: list[float] = []
    last_total = None
    for _ in range(N2_QUERY_COUNT):
        start = time.perf_counter()
        resp = await _admin(client, token, "GET", "/admin/audit", params=params)
        latencies_ms.append((time.perf_counter() - start) * 1000)
        payload = resp.json()
        last_total = payload["total"]
        assert len(payload["items"]) <= 50

    assert last_total == N2_VOLUME, f"expected {N2_VOLUME} rows in window, got {last_total}"
    latencies_ms.sort()
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
    print(
        f"N2 volume={N2_VOLUME} window_days={N2_WINDOW_DAYS} queries={N2_QUERY_COUNT} "
        f"p95_ms={p95:.2f} min_ms={latencies_ms[0]:.2f} max_ms={latencies_ms[-1]:.2f}"
    )
    assert p95 <= 5000, f"p95 latency was {p95:.2f}ms, expected <= 5000ms"


# ---------- N3: Revocation Propagation (≤60s) ----------

@pytest.mark.asyncio
async def test_n3_revocation_propagation(test_db, n_client):
    """N3: POST /admin/sessions/revoke → Block A validate_token rejects within ≤60s."""
    client, tenant, _admin_user, token = n_client

    member = await native_auth_service.create_native_user(
        email=f"member@{tenant.subdomain}.com",
        password="SecurePass123!",
        display_name="Member",
        tenant_id=tenant.tenant_id,
        db_session=test_db,
        role="member",
        invited_by=_admin_user.principal_id,
    )
    member_token = await token_service.issue_access_token(
        str(tenant.tenant_id),
        str(member.principal_id),
        scopes_for_role("member"),
        role="member",
        token_version=int(member.token_version or 0),
    )
    payload = await token_service.validate_token(member_token)
    assert payload["sub"] == str(member.principal_id)

    resp = await _admin(
        client,
        token,
        "POST",
        "/admin/sessions/revoke",
        json={"user_id": str(member.principal_id)},
    )
    assert resp.json()["revoked"] is True

    start = time.perf_counter()
    deadline = start + 60.0
    elapsed = None
    while time.perf_counter() < deadline:
        try:
            await token_service.validate_token(member_token)
        except RevokedTokenError:
            elapsed = time.perf_counter() - start
            break
        await asyncio.sleep(0.05)

    assert elapsed is not None, "token still valid 60s after POST /admin/sessions/revoke"
    print(f"N3 elapsed_s={elapsed:.4f} token_version={resp.json()['token_version']}")
    assert elapsed <= 60.0, f"revocation took {elapsed:.4f}s, expected <= 60s"
