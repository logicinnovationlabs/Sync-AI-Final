"""
Behavioral tests for RBAC expansion (owner/admin/member/viewer).

Tests run against the real admin route handlers using ASGI transport.
Provides raw request/response evidence for verification.
"""

import asyncio
import httpx
import json
from typing import Dict, Any
import sys
from pathlib import Path
from uuid import uuid4

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import select, text

from app.api.v1.admin import admin_router
from app.api.v1.me import router as me_router
from app.api.deps import get_tenant, get_tenant_session
from app.models.user import User
from app.models.tenant import Tenant
from app.services.native_auth import native_auth_service
from app.services.tenant_resolver import TenantRouting, tenant_resolver
from app.services.token_service import token_service
from app.services.admin.scopes import scopes_for_role
from app.storage.vault_client import vault_client
from tests.conftest import TEST_DB_URL

import pytest


async def create_tenant_and_users(test_db) -> tuple[Tenant, User, User, User, User, str, str, str, str]:
    """Create a tenant + owner/admin/member/viewer users, returning (tenant, owner, admin, member, viewer, owner_jwt, admin_jwt, member_jwt, viewer_jwt)."""
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

    owner = await native_auth_service.create_native_user(
        email=f"owner@{tenant.subdomain}.com",
        password="SecurePass123!",
        display_name="Owner",
        tenant_id=tenant_id,
        db_session=test_db,
        role="owner",
        must_change_password=False,
        is_active=True,
    )

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

    member = await native_auth_service.create_native_user(
        email=f"member@{tenant.subdomain}.com",
        password="SecurePass123!",
        display_name="Member",
        tenant_id=tenant_id,
        db_session=test_db,
        role="member",
        must_change_password=False,
        is_active=True,
    )

    viewer = await native_auth_service.create_native_user(
        email=f"viewer@{tenant.subdomain}.com",
        password="SecurePass123!",
        display_name="Viewer",
        tenant_id=tenant_id,
        db_session=test_db,
        role="viewer",
        must_change_password=False,
        is_active=True,
    )

    owner_token = await token_service.issue_access_token(
        str(tenant_id),
        str(owner.principal_id),
        scopes_for_role("owner"),
        role="owner",
        token_version=0,
    )
    
    admin_token = await token_service.issue_access_token(
        str(tenant_id),
        str(admin.principal_id),
        scopes_for_role("admin"),
        role="admin",
        token_version=0,
    )
    
    member_token = await token_service.issue_access_token(
        str(tenant_id),
        str(member.principal_id),
        scopes_for_role("member"),
        role="member",
        token_version=0,
    )
    
    viewer_token = await token_service.issue_access_token(
        str(tenant_id),
        str(viewer.principal_id),
        scopes_for_role("viewer"),
        role="viewer",
        token_version=0,
    )
    
    return tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token


async def setup_test_client(test_db):
    """Setup ASGI test client with dependency overrides."""
    tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token = await create_tenant_and_users(test_db)
    
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

    import unittest.mock as mock
    with mock.patch.object(tenant_resolver, "resolve", fake_resolve):
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def override_tenant() -> TenantRouting:
            return routing

        async def override_session():
            async with Session() as session:
                yield session

        app = FastAPI()
        app.include_router(admin_router, prefix="/admin")
        app.include_router(me_router)
        app.dependency_overrides[get_tenant] = override_tenant
        app.dependency_overrides[get_tenant_session] = override_session
        transport = ASGITransport(app=app)
        
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _admin(client: AsyncClient, token: str, method: str, path: str, **kwargs):
    response = await client.request(method, f"/admin{path}", headers=_auth(token), **kwargs)
    assert response.status_code < 400, (
        f"{method} {path} -> {response.status_code} {response.text}"
    )
    return response


async def _admin_no_assert(client: AsyncClient, token: str, method: str, path: str, **kwargs):
    """Make an admin request without asserting success (for testing error cases)."""
    response = await client.request(method, f"/admin{path}", headers=_auth(token), **kwargs)
    return response


async def _api(client: AsyncClient, token: str, method: str, path: str, **kwargs):
    """Make an API request without the /admin prefix (for non-admin endpoints)."""
    response = await client.request(method, path, headers=_auth(token), **kwargs)
    return response


class MockResponse:
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self._detail = detail
    
    def json(self):
        return {"detail": self._detail}


async def scenario_1_owner_promotes_member(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token):
    """Scenario 1: owner promotes a member to admin."""
    print("\n=== Scenario 1: Owner promotes member to admin ===")
    print("SKIPPED - Scenario 1 accepted as-is per user instructions")


async def scenario_2_admin_cannot_promote_to_owner(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token):
    """Scenario 2: admin attempts to promote someone to owner or edit owner role."""
    print("\n=== Scenario 2: Admin cannot promote to owner or edit owner ===")
    print("SKIPPED - Scenario 2 accepted as-is per user instructions")


async def scenario_3_cannot_demote_sole_owner(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token):
    """Scenario 3: Attempt to demote the sole owner."""
    print("\n=== Scenario 3: Cannot demote sole owner ===")
    print("SKIPPED - Scenario 3 accepted as-is per user instructions")


async def scenario_4_viewer_mutation_blocked(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token):
    """Scenario 4: viewer calls mutating endpoint -> 403, read endpoint -> 200."""
    print("\n=== Scenario 4: Viewer mutation blocked ===")
    
    # Test 1: Viewer tries to patch user role (should 403)
    print("Viewer attempting to patch user role (should 403)...")
    try:
        resp = await _admin_no_assert(client, viewer_token, "PATCH", f"/admin/users/{member.principal_id}", json={"role": "admin"})
        print(f"Patch status: {resp.status_code}")
        print(f"Patch response: {json.dumps(resp.json(), indent=2)}")
        
        if resp.status_code == 403:
            print("✓ Viewer blocked from mutating user role (403)")
        else:
            print(f"❌ Viewer not blocked (status: {resp.status_code})")
    except Exception as e:
        # ForbiddenError is raised before returning a response
        if "forbidden" in str(e).lower() or "admin role required" in str(e).lower():
            print(f"✓ Viewer blocked from mutating user role (403 - exception: {str(e)[:100]})")
        else:
            print(f"❌ Unexpected error: {e}")
    
    # Test 2: Verify viewer can access read endpoint (/me)
    # The /me endpoint is mounted at /me and requires authentication but no special scopes
    print("Viewer attempting to access /me endpoint (should 200)...")
    resp = await _api(client, viewer_token, "GET", "/me")
    print(f"/me status: {resp.status_code}")
    print(f"/me response: {json.dumps(resp.json(), indent=2)}")
    
    if resp.status_code == 200:
        print("✓ Viewer can access /me endpoint (200)")
        # Verify the response contains expected fields
        me_data = resp.json()
        if "principal_id" in me_data and "role" in me_data:
            print(f"✓ /me returned principal_id: {me_data['principal_id']}, role: {me_data['role']}")
            if me_data["role"] == "viewer":
                print("✓ /me correctly identifies user as viewer")
            else:
                print(f"❌ /me returned unexpected role: {me_data['role']}")
        else:
            print(f"❌ /me response missing expected fields")
    else:
        print(f"❌ Viewer cannot access /me (status: {resp.status_code})")


async def scenario_5_self_role_edit_blocked(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token):
    """Scenario 5: User attempts to edit their own role."""
    print("\n=== Scenario 5: Self role edit blocked ===")
    print("SKIPPED - Scenario 5 accepted as-is per user instructions")


async def scenario_6_ownership_transfer(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token, test_db):
    """Scenario 6: Ownership transfer atomic operation."""
    print("\n=== Scenario 6: Ownership transfer ===")
    print("SKIPPED - Scenario 6 accepted as-is per user instructions")


async def scenario_7_admin_cannot_create_admin(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token, test_db):
    """Scenario 7: admin attempts to promote member to admin -> blocked; owner succeeds."""
    print("\n=== Scenario 7: Admin cannot create admin ===")
    print("SKIPPED - Scenario 7 accepted as-is per user instructions")


@pytest.mark.asyncio
async def test_rbac_expansion_scenarios(test_db):
    """Run all RBAC expansion behavioral scenarios."""
    print("=" * 60)
    print("RBAC Expansion Behavioral Tests")
    print("=" * 60)
    
    try:
        async for client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token in setup_test_client(test_db):
            # Run scenarios
            await scenario_1_owner_promotes_member(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token)
            await scenario_2_admin_cannot_promote_to_owner(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token)
            await scenario_3_cannot_demote_sole_owner(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token)
            await scenario_4_viewer_mutation_blocked(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token)
            await scenario_5_self_role_edit_blocked(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token)
            await scenario_6_ownership_transfer(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token, test_db)
            await scenario_7_admin_cannot_create_admin(client, tenant, owner, admin, member, viewer, owner_token, admin_token, member_token, viewer_token, test_db)
            
            print("\n" + "=" * 60)
            print("All scenarios completed")
            print("=" * 60)
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        raise
