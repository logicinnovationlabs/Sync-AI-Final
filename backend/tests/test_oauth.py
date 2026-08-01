"""
Unit tests for OAuth service.
"""

import pytest
from uuid import uuid4

from app.services.oauth_service import oauth_service


@pytest.mark.asyncio
async def test_oauth_create_authorization_code():
    """Test creating an authorization code."""
    tenant_id = str(uuid4())
    principal_id = str(uuid4())
    
    code = await oauth_service.create_authorization_code(
        client_id="test_client",
        redirect_uri="http://localhost:3000/callback",
        code_challenge="challenge123",
        code_challenge_method="S256",
        tenant_id=tenant_id,
        principal_id=principal_id,
        scopes=["search.read"],
    )
    
    assert isinstance(code, str)
    assert len(code) > 0


@pytest.mark.asyncio
async def test_oauth_client_credentials_stub():
    """Test client_credentials flow (stub)."""
    # This is a stub; full implementation requires prod code
    pass
