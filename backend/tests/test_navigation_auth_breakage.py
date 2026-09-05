"""
Test to prove that /authorize endpoint breaks after navigation change.

This test simulates exactly what a real browser sends on top-level navigation:
- No Authorization header (browsers don't send custom headers on navigation)
- Only whatever cookies would realistically be present

Expected result: 401 Unauthorized because get_current_user requires Authorization header.
"""

import pytest
from unittest.mock import MagicMock, patch
from app.main import app
from fastapi.testclient import TestClient


def test_authorize_endpoint_fails_without_auth_header():
    """
    Prove that /authorize endpoint 401s on real browser navigation.
    
    Real browser navigation (window.location.href) cannot send custom headers.
    The endpoint depends on get_current_user which requires Authorization header.
    """
    client = TestClient(app)
    
    # Simulate real browser navigation: no Authorization header
    response = client.get(
        "/connectors/google/authorize",
        follow_redirects=False,
    )
    
    # Should fail with 401 because get_current_user requires Authorization header
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    assert "Not authenticated" in response.text or "unauthorized" in response.text.lower()


def test_authorize_endpoint_succeeds_with_auth_header():
    """
    Prove that /authorize endpoint works with Authorization header (XHR pattern).

    This is what the frontend does: XHR call with JWT, receives JSON with authorization_url.
    The backend sets the oauth_binding cookie on this response.
    """
    client = TestClient(app)

    # Mock token validation to return a valid payload
    mock_payload = {
        "tenant_id": "test-tenant-123",
        "sub": "user-123",
        "user_id": "user-123",
        "scopes": ["connectors.write"],
        "jti": "test-jti-456",
    }

    with patch("app.services.token_service.token_service.validate_token") as mock_validate, \
         patch("app.connectors.google.oauth_state._sync_redis") as mock_redis, \
         patch("app.services.tenant_resolver.tenant_resolver.resolve") as mock_resolve:
        mock_validate.return_value = mock_payload
        mock_redis.return_value = MagicMock()
        mock_resolve.return_value = MagicMock(tenant_id="test-tenant-123")

        response = client.get(
            "/connectors/google/authorize",
            headers={"Authorization": "Bearer fake-token"},
            follow_redirects=False,
        )

        # Should succeed with 200 JSON when Authorization header is present
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "authorization_url" in data
        assert "tenant_id" in data
        # Cookie should be set on the response
        assert "oauth_binding" in response.cookies


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
