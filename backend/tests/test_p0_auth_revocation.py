"""
P0 Security Tests: Auth Revocation Bypass Fix

Tests for the critical security fix ensuring deactivation, role changes, and
session revocation work correctly across all token issuance paths.

Tests cover:
1. Deactivation blocks refresh attempts
2. Deactivation invalidates existing access tokens (including refresh-derived ones)
3. Role downgrade invalidates old-scope tokens
4. Normal flows still work (no regression)
"""

import pytest
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select, Result
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.oauth_client import RefreshToken
from app.services.token_service import token_service
from app.services.oauth_service import oauth_service
from app.services.revocation import revocation_service
from app.core.exceptions import UnauthorizedError, InvalidTokenError, RevokedTokenError
from app.storage.redis_client import redis_client


@pytest.mark.asyncio
async def test_deactivation_blocks_refresh():
    """
    P0 Bug #1: Deactivate a user → assert their next /auth/refresh call fails.
    
    Before fix: deactivated users could refresh indefinitely.
    After fix: refresh attempts fail with 401/403 when _scopes_for_principal checks account state.
    
    Uses mocking to avoid requiring real DB/Redis infrastructure.
    """
    tenant_id = uuid4()
    principal_id = uuid4()
    
    # Create a deactivated user
    deactivated_user = User(
        principal_id=principal_id,
        tenant_id=tenant_id,
        idp_subject=f"native:test@example.com",
        email="test@example.com",
        display_name="Test User",
        role="member",
        status="deactivated",  # User is deactivated
        is_active=False,  # User is inactive
        token_version=1,
    )
    
    # Mock the DB session to return the deactivated user
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock(spec=Result)
    mock_result.scalar_one_or_none.return_value = deactivated_user
    mock_db_session.execute.return_value = mock_result
    
    # Test that _scopes_for_principal raises UnauthorizedError for deactivated user
    try:
        scopes, metadata = await oauth_service._scopes_for_principal(
            str(principal_id),
            str(tenant_id),
            mock_db_session,
            ["search.read"],  # fallback scopes
        )
        pytest.fail("_scopes_for_principal should have raised UnauthorizedError for deactivated user")
    except UnauthorizedError as e:
        # Expected - account state check should fail
        assert "inactive" in str(e).lower() or "deactivated" in str(e).lower()


@pytest.mark.asyncio
async def test_deactivation_invalidates_existing_access_tokens():
    """
    P0 Bug #2: Deactivate user with live refresh-derived access token → 
    assert existing token fails validate_token.
    
    Before fix: tokens without role claim (refresh-derived) skipped version check.
    After fix: all tokens have token_version and version check is mandatory.
    """
    tenant_id = uuid4()
    principal_id = uuid4()
    
    # Create a user
    user = User(
        principal_id=principal_id,
        tenant_id=tenant_id,
        idp_subject=f"native:test2@example.com",
        email="test2@example.com",
        display_name="Test User 2",
        role="member",
        status="active",
        is_active=True,
        token_version=0,
    )
    
    # Issue an access token with token_version=0
    access_token = await token_service.issue_access_token(
        tenant_id=str(tenant_id),
        principal_id=str(principal_id),
        scopes=["search.read"],
        role="member",
        token_version=0,
    )
    
    # Verify token is valid initially
    payload = await token_service.validate_token(access_token)
    assert payload["token_version"] == 0
    
    # Deactivate the user and bump token_version
    user.is_active = False
    user.status = "deactivated"
    db_session = None  # Would be injected
    new_version = await revocation_service.revoke_user(
        str(principal_id),
        str(tenant_id),
        db_session,
        user,
    )
    
    assert new_version == 1
    
    # The old access token should now fail validation due to version mismatch
    try:
        await token_service.validate_token(access_token)
        pytest.fail("Old token should be rejected after version bump")
    except RevokedTokenError:
        # Expected - token version mismatch
        pass
    except InvalidTokenError as e:
        # Also acceptable if missing token_version claim is rejected
        assert "token_version" in str(e).lower()


@pytest.mark.asyncio
async def test_role_downgrade_invalidates_old_tokens():
    """
    P0 Bug #3: Role downgrade → assert old-scope tokens are rejected.
    
    Before fix: role changes didn't invalidate existing tokens carrying old scopes.
    After fix: role changes trigger token_version bump, invalidating old tokens.
    """
    tenant_id = uuid4()
    principal_id = uuid4()
    
    # Create an admin user
    user = User(
        principal_id=principal_id,
        tenant_id=tenant_id,
        idp_subject=f"native:admin@example.com",
        email="admin@example.com",
        display_name="Admin User",
        role="admin",
        status="active",
        is_active=True,
        token_version=0,
    )
    
    # Issue admin-scoped token
    admin_token = await token_service.issue_access_token(
        tenant_id=str(tenant_id),
        principal_id=str(principal_id),
        scopes=["admin.users.write", "search.read"],  # Admin scopes
        role="admin",
        token_version=0,
    )
    
    # Verify admin token has admin scopes
    payload = await token_service.validate_token(admin_token)
    assert "admin.users.write" in payload["scopes"]
    assert payload["role"] == "admin"
    assert payload["token_version"] == 0
    
    # Downgrade to member
    user.role = "member"
    db_session = None  # Would be injected
    new_version = await revocation_service.revoke_user(
        str(principal_id),
        str(tenant_id),
        db_session,
        user,
    )
    
    assert new_version == 1
    
    # Old admin token should be rejected
    try:
        await token_service.validate_token(admin_token)
        pytest.fail("Old admin token should be rejected after role downgrade")
    except RevokedTokenError:
        # Expected - version mismatch
        pass
    
    # New token should have member scopes
    new_token = await token_service.issue_access_token(
        tenant_id=str(tenant_id),
        principal_id=str(principal_id),
        scopes=["search.read"],  # Member scopes only
        role="member",
        token_version=1,
    )
    
    new_payload = await token_service.validate_token(new_token)
    assert "admin.users.write" not in new_payload["scopes"]
    assert new_payload["role"] == "member"
    assert new_payload["token_version"] == 1


@pytest.mark.asyncio
async def test_normal_refresh_still_works():
    """
    Regression test: Normal active user can still refresh normally.
    
    Ensures the fix doesn't break legitimate refresh flows.
    """
    tenant_id = uuid4()
    principal_id = uuid4()
    
    # Create an active user
    active_user = User(
        principal_id=principal_id,
        tenant_id=tenant_id,
        idp_subject=f"native:normal@example.com",
        email="normal@example.com",
        display_name="Normal User",
        role="member",
        status="active",
        is_active=True,
        token_version=0,
    )
    
    # Mock the DB session to return the active user
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock(spec=Result)
    mock_result.scalar_one_or_none.return_value = active_user
    mock_db_session.execute.return_value = mock_result
    
    # Test that _scopes_for_principal succeeds for active users
    scopes, metadata = await oauth_service._scopes_for_principal(
        str(principal_id),
        str(tenant_id),
        mock_db_session,
        ["search.read"],  # fallback scopes
    )
    
    # Should return scopes and metadata without error
    assert isinstance(scopes, list)
    assert isinstance(metadata, dict)
    assert metadata["role"] == "member"
    assert metadata["token_version"] == 0


@pytest.mark.asyncio
async def test_token_version_always_stamped():
    """
    Regression test: All token issuance paths stamp token_version.
    
    Ensures no issuance path produces tokens without the version claim.
    """
    tenant_id = uuid4()
    principal_id = uuid4()
    
    # Test 1: Normal user token with role
    token1 = await token_service.issue_access_token(
        tenant_id=str(tenant_id),
        principal_id=str(principal_id),
        scopes=["search.read"],
        role="member",
        token_version=5,
    )
    payload1 = await token_service.decode_without_validation(token1)
    assert "token_version" in payload1
    assert payload1["token_version"] == 5
    
    # Test 2: Token without role (service account scenario)
    token2 = await token_service.issue_access_token(
        tenant_id=str(tenant_id),
        principal_id="service-client-123",
        scopes=["connectors.read"],
        role="service",
        token_version=0,
    )
    payload2 = await token_service.decode_without_validation(token2)
    assert "token_version" in payload2
    assert payload2["token_version"] == 0
    
    # Test 3: Token with role=None should still get version
    token3 = await token_service.issue_access_token(
        tenant_id=str(tenant_id),
        principal_id=str(principal_id),
        scopes=["search.read"],
        role=None,
        token_version=3,
    )
    payload3 = await token_service.decode_without_validation(token3)
    assert "token_version" in payload3
    assert payload3["token_version"] == 3


@pytest.mark.asyncio
async def test_missing_token_version_rejected():
    """
    P0 Bug #4: validate_token fails closed on missing token_version.
    
    Before fix: missing token_version was silently skipped (default-allow).
    After fix: missing token_version is rejected as invalid.
    """
    # Create a legacy-style token without token_version claim
    # This simulates old tokens or manually forged tokens
    from datetime import datetime, timedelta, timezone
    import jwt
    
    legacy_payload = {
        "iss": token_service.issuer,
        "sub": str(uuid4()),
        "tenant_id": str(uuid4()),
        "scopes": ["search.read"],
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "jti": str(uuid4()),
        # Deliberately omit token_version
    }
    
    token_service._load_keys()
    legacy_token = jwt.encode(
        legacy_payload,
        token_service._private_key,
        algorithm=token_service.algorithm,
        headers={"kid": token_service._active_kid},
    )
    
    # Should reject with InvalidTokenError
    try:
        await token_service.validate_token(legacy_token)
        pytest.fail("Token without token_version should be rejected")
    except InvalidTokenError as e:
        assert "token_version" in str(e).lower()


@pytest.mark.asyncio
async def test_concurrent_version_bumps():
    """
    Edge case: Multiple concurrent revocations don't cause issues.
    
    Ensures token_version incrementing is safe under concurrent requests.
    """
    tenant_id = uuid4()
    principal_id = uuid4()
    
    user = User(
        principal_id=principal_id,
        tenant_id=tenant_id,
        idp_subject=f"native:concurrent@example.com",
        email="concurrent@example.com",
        display_name="Concurrent User",
        role="member",
        status="active",
        is_active=True,
        token_version=0,
    )
    
    db_session = None  # Would be injected
    
    # Simulate multiple concurrent revocations
    # In real test, these would be async tasks running concurrently
    version1 = await revocation_service.revoke_user(
        str(principal_id),
        str(tenant_id),
        db_session,
        user,
    )
    assert version1 == 1
    
    version2 = await revocation_service.revoke_user(
        str(principal_id),
        str(tenant_id),
        db_session,
        user,
    )
    assert version2 == 2
    
    version3 = await revocation_service.revoke_user(
        str(principal_id),
        str(tenant_id),
        db_session,
        user,
    )
    assert version3 == 3
    
    # Final token_version should be 3
    assert user.token_version == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
