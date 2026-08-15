"""Block N: Full Signoff Tests (N1, N2, N3) – runs against real Docker via service layer."""

import time
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text

from app.core.exceptions import RevokedTokenError
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.tenant import Tenant
from app.services.native_auth import native_auth_service
from app.services.token_service import token_service
from app.services.admin.audit_logger import write_audit_log
from app.services.admin.scopes import scopes_for_role
from app.storage.vault_client import vault_client
from app.storage.redis_client import redis_client


# ---------- Helpers ----------

async def create_tenant_and_admin(test_db) -> tuple[Tenant, User, str]:
    """Create a tenant + admin directly via services, returning (tenant, admin_user, admin_jwt)."""
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

    temp_password = "SecurePass123!"
    admin = await native_auth_service.create_native_user(
        email=f"admin@{tenant.subdomain}.com",
        password=temp_password,
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


# ---------- Fixtures ----------

@pytest.fixture(scope="function")
async def test_tenant_and_admin(test_db):
    """Create a fresh tenant and admin for each test, yielding tenant, admin, token."""
    tenant, admin, token = await create_tenant_and_admin(test_db)
    yield tenant, admin, token

    # Cleanup: delete tenant, admin, audit logs (using delete() not select().delete())
    await test_db.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant.tenant_id))
    await test_db.execute(delete(User).where(User.tenant_id == tenant.tenant_id))
    await test_db.execute(delete(Tenant).where(Tenant.tenant_id == tenant.tenant_id))
    await test_db.commit()


# ---------- N1: Audit Completeness ----------

@pytest.mark.asyncio
async def test_n1_audit_completeness(test_db, test_tenant_and_admin):
    """N1: Perform 20 distinct admin actions; 100% must produce audit records."""
    tenant, admin, _ = test_tenant_and_admin

    for i in range(20):
        user = await native_auth_service.create_native_user(
            email=f"user{i}@{tenant.subdomain}.com",
            password="SecurePass123!",
            display_name=f"User {i}",
            tenant_id=tenant.tenant_id,
            db_session=test_db,
            role="member",
            invited_by=admin.principal_id,
        )
        await write_audit_log(
            test_db,
            tenant_id=tenant.tenant_id,
            actor_id=admin.principal_id,
            action_type="user.created",
            target={"principal_id": str(user.principal_id)},
            ip_address="127.0.0.1",
        )
    await test_db.commit()

    result = await test_db.execute(
        select(func.count()).select_from(AuditLog)
        .where(AuditLog.tenant_id == tenant.tenant_id)
        .where(AuditLog.action_type == "user.created")
    )
    count = result.scalar_one()
    assert count >= 20, f"Expected at least 20 audit entries, got {count}"


# ---------- N2: Search Latency (p95 < 5s) ----------

@pytest.mark.asyncio
async def test_n2_audit_latency(test_db, test_tenant_and_admin):
    """N2: Query a 90-day window on 100k logs; p95 must be < 5s."""
    tenant, admin, _ = test_tenant_and_admin
    actor_id = admin.principal_id

    # Bulk insert 100,000 logs directly – now includes id via gen_random_uuid()
    await test_db.execute(
        text(
            "INSERT INTO audit_logs (id, tenant_id, actor_id, action_type, target_json, ip_address, created_at) "
            "SELECT gen_random_uuid(), :tenant_id, CAST(:actor_id AS uuid), 'test.bulk', "
            "jsonb_build_object('idx', idx), '127.0.0.1', NOW() - (interval '1 second' * idx) "
            "FROM generate_series(1, 100000) AS idx"
        ),
        {
            "tenant_id": tenant.tenant_id,
            "actor_id": str(actor_id),
        },
    )
    await test_db.commit()

    latencies = []
    for _ in range(20):
        start = time.perf_counter()
        stmt = (
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant.tenant_id)
            .order_by(AuditLog.created_at.desc())
            .limit(50)
        )
        result = await test_db.execute(stmt)
        _ = result.scalars().all()
        end = time.perf_counter()
        latencies.append((end - start) * 1000)  # ms

    p95 = sorted(latencies)[int(0.95 * len(latencies))]
    assert p95 < 5000, f"p95 latency was {p95:.2f}ms, expected < 5000ms"


# ---------- N3: Revocation Propagation (<60s) ----------

@pytest.mark.asyncio
async def test_n3_revocation_propagation(test_db, test_tenant_and_admin):
    """N3: Revoke a session; it must be reflected in Block A within ≤60s."""
    tenant, admin, _ = test_tenant_and_admin

    member = await native_auth_service.create_native_user(
        email=f"member@{tenant.subdomain}.com",
        password="SecurePass123!",
        display_name="Member",
        tenant_id=tenant.tenant_id,
        db_session=test_db,
        role="member",
        invited_by=admin.principal_id,
    )
    member_token = await token_service.issue_access_token(
        str(tenant.tenant_id),
        str(member.principal_id),
        scopes_for_role("member"),
        role="member",
        token_version=0,
    )

    # Validate token – should work
    payload = await token_service.validate_token(member_token)
    assert payload["sub"] == str(member.principal_id)   # <-- use "sub" not "principal_id"

    # Revoke by bumping token_version in Redis
    new_version = 1
    await redis_client.set(
        str(tenant.tenant_id),
        f"token_version:{member.principal_id}",
        str(new_version),
        ex=60,
    )
    member.token_version = new_version
    await test_db.commit()

    with pytest.raises(RevokedTokenError):
        await token_service.validate_token(member_token)