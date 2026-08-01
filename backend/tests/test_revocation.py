"""
Unit tests for revocation service.
"""

import pytest
from uuid import uuid4

from app.services.token_service import token_service
from app.services.revocation import revocation_service
from app.storage.redis_client import redis_client


@pytest.mark.asyncio
async def test_revoke_token_adds_to_redis_set(test_redis):
    """Test token revocation adds jti to Redis revoked set."""
    tenant_id = str(uuid4())
    principal_id = str(uuid4())
    
    # Issue token
    token = await token_service.issue_access_token(
        tenant_id=tenant_id,
        principal_id=principal_id,
        scopes=[],
    )
    
    # Decode to get jti
    payload = await token_service.decode_without_validation(token)
    jti = payload["jti"]
    
    # Revoke token
    await test_redis.sadd(tenant_id, f"revoked:{jti}", jti)
    
    # Check if jti is in revoked set
    is_revoked = await test_redis.sismember(tenant_id, f"revoked:{jti}", jti)
    
    assert is_revoked


@pytest.mark.asyncio
async def test_revoked_token_fails_validation(test_redis):
    """Test that revoked tokens fail validation (A2)."""
    tenant_id = str(uuid4())
    principal_id = str(uuid4())
    
    # Issue token
    token = await token_service.issue_access_token(
        tenant_id=tenant_id,
        principal_id=principal_id,
        scopes=[],
    )
    
    # Validate initially (should pass)
    payload = await token_service.validate_token(token)
    assert payload["jti"] is not None
    
    # Revoke token
    jti = payload["jti"]
    await redis_client.sadd(tenant_id, f"revoked:{jti}", jti)
    
    # Validate again (should fail)
    from app.core.exceptions import RevokedTokenError
    with pytest.raises(RevokedTokenError):
        await token_service.validate_token(token)

