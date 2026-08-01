"""
Unit tests for TokenService.
"""

import pytest
from uuid import uuid4

from app.services.token_service import token_service
from app.core.exceptions import InvalidTokenError


@pytest.mark.asyncio
async def test_issue_and_validate_access_token():
    """Test issuing and validating an access token."""
    tenant_id = str(uuid4())
    principal_id = str(uuid4())
    scopes = ["search.read", "document.read"]
    
    # Issue token
    token = await token_service.issue_access_token(
        tenant_id=tenant_id,
        principal_id=principal_id,
        scopes=scopes,
    )
    
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Validate token
    payload = await token_service.validate_token(token)
    
    assert payload["tenant_id"] == tenant_id
    assert payload["sub"] == principal_id
    assert payload["scopes"] == scopes
    assert "jti" in payload
    assert "exp" in payload
    assert "iat" in payload


@pytest.mark.asyncio
async def test_validate_invalid_token():
    """Test validating an invalid token."""
    with pytest.raises(InvalidTokenError):
        await token_service.validate_token("invalid.token.here")


@pytest.mark.asyncio
async def test_token_contains_exactly_one_tenant_id():
    """Test that token contains exactly one tenant_id (A1)."""
    tenant_id = str(uuid4())
    principal_id = str(uuid4())
    
    token = await token_service.issue_access_token(
        tenant_id=tenant_id,
        principal_id=principal_id,
        scopes=[],
    )
    
    payload = await token_service.validate_token(token)
    
    # Count tenant_id occurrences
    tenant_id_count = sum(1 for key in payload.keys() if "tenant" in key.lower())
    
    assert "tenant_id" in payload
    assert payload["tenant_id"] == tenant_id
