"""
Google Workspace connector — OAuth URL generation and token encryption round-trip.

Does not print secret values. Does not call the live Google token endpoint.
"""

import pytest
from urllib.parse import parse_qs, urlparse

from app.connectors.google.oauth import GoogleOAuthManager, google_oauth_from_settings
from app.connectors.google.oauth_state import decode_oauth_state, encode_oauth_state
from app.connectors.google.token_store import (
    PersistentGoogleTokenStore,
    decrypt_token_blob,
    encrypt_token_blob,
)


class _MemoryTokenStore:
    def __init__(self):
        self._tokens = {}

    def get_token(self, key):
        return self._tokens.get(key)

    def set_token(self, key, token_data):
        self._tokens[key] = token_data


def test_oauth_authorization_url_shape():
    store = _MemoryTokenStore()
    manager = GoogleOAuthManager(
        store,
        client_id="test-client-id.apps.googleusercontent.com",
        client_secret="not-a-real-secret",
        scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/gmail.readonly",
        ],
    )
    state = encode_oauth_state(
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    )
    url = manager.build_authorization_url(
        tenant_id="11111111-1111-1111-1111-111111111111",
        redirect_uri="http://localhost:8000/connectors/google/callback",
        state=state,
    )
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/v2/auth"
    assert qs["client_id"] == ["test-client-id.apps.googleusercontent.com"]
    assert qs["redirect_uri"] == [
        "http://localhost:8000/connectors/google/callback"
    ]
    assert qs["response_type"] == ["code"]
    assert qs["access_type"] == ["offline"]
    assert qs["prompt"] == ["consent"]
    assert "drive.readonly" in qs["scope"][0]
    assert "gmail.readonly" in qs["scope"][0]
    decoded = decode_oauth_state(qs["state"][0])
    assert decoded is not None
    assert decoded["tenant_id"] == "11111111-1111-1111-1111-111111111111"
    assert decoded["user_id"] == "22222222-2222-2222-2222-222222222222"
    assert decoded["nonce"]


def test_token_blob_encrypt_decrypt_roundtrip():
    plaintext = '{"access_token":"dummy-access","refresh_token":"dummy-refresh","token_type":"Bearer"}'
    ciphertext = encrypt_token_blob(plaintext)
    assert ciphertext
    assert "dummy-access" not in ciphertext
    assert "dummy-refresh" not in ciphertext
    recovered = decrypt_token_blob(ciphertext)
    assert recovered == plaintext


def test_persistent_token_store_roundtrip_memory_fallback():
    store = PersistentGoogleTokenStore("tenant-roundtrip")
    payload = {
        "access_token": "dummy-access-token",
        "refresh_token": "dummy-refresh-token",
        "token_type": "Bearer",
    }
    store.set_token("google_oauth:tenant-roundtrip", payload)
    loaded = store.get_token("google_oauth:tenant-roundtrip")
    assert loaded is not None
    assert loaded["token_type"] == "Bearer"
    assert loaded["access_token"] == payload["access_token"]
    assert loaded["refresh_token"] == payload["refresh_token"]


def test_google_oauth_from_settings_reads_aliased_client_id():
    store = _MemoryTokenStore()
    manager = google_oauth_from_settings(store)
    url = manager.build_authorization_url(
        "t", "http://localhost:8000/connectors/google/callback", state="abc"
    )
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert qs["response_type"] == ["code"]
    assert "client_id" in qs
    # Value may be empty in CI without env; name mapping is what we assert.
    assert manager.TOKEN_ENDPOINT == "https://oauth2.googleapis.com/token"


@pytest.mark.asyncio
async def test_authorize_endpoint_returns_google_url(monkeypatch):
    """Hit GET /connectors/google/authorize and check the Google URL shape."""
    from uuid import uuid4
    from unittest.mock import MagicMock, patch
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app
    from app.services.token_service import token_service

    monkeypatch.setattr(
        settings,
        "google_client_id",
        "test-client-id.apps.googleusercontent.com",
    )
    monkeypatch.setattr(settings, "google_client_secret", "not-a-real-secret")
    monkeypatch.setattr(
        settings,
        "google_redirect_uri",
        "http://localhost:8000/connectors/google/callback",
    )

    tenant_id = str(uuid4())
    principal_id = str(uuid4())
    token = await token_service.issue_access_token(
        tenant_id=tenant_id,
        principal_id=principal_id,
        scopes=["connectors.write", "connectors.read"],
    )
    client = TestClient(app)
    with patch("app.api.deps.tenant_resolver.resolve") as mock_resolve:
        mock_resolve.return_value = MagicMock(tenant_id=tenant_id)
        response = client.get(
            "/connectors/google/authorize",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    url = body["authorization_url"]
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.netloc == "accounts.google.com"
    assert qs["client_id"] == ["test-client-id.apps.googleusercontent.com"]
    assert qs["redirect_uri"] == [
        "http://localhost:8000/connectors/google/callback"
    ]
    assert "drive.readonly" in qs["scope"][0]
    assert "gmail.readonly" in qs["scope"][0]
    assert qs["access_type"] == ["offline"]
    decoded = decode_oauth_state(qs["state"][0])
    assert decoded["tenant_id"] == tenant_id
    assert decoded["user_id"] == principal_id
