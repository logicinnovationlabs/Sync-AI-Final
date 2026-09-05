"""Google auto-sync: OAuth callback enqueue + ingest.raw.v1 publisher."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.connectors.google.oauth_state import encode_oauth_state
from app.services.ingest.publisher import publish_raw_event, raw_event_from_item
from app.workers.tasks import backfill_source


def test_backfill_source_is_importable():
    assert callable(backfill_source.delay)
    assert backfill_source.name == "app.workers.tasks.backfill_source"


def test_raw_event_from_drive_item():
    event = raw_event_from_item(
        tenant_id="t1",
        source_type="google_drive",
        source_instance_id="kv/tenant-t1/google-oauth",
        item={
            "id": "file-1",
            "name": "Roadmap",
            "permissions": [{"emailAddress": "owner@example.com", "role": "owner"}],
        },
    )
    assert event["source_object_id"] == "file-1"
    assert event["object_kind"] == "file"
    assert event["raw_payload"]["name"] == "Roadmap"
    assert event["identity_refs"][0]["value"] == "owner@example.com"


def test_publish_raw_event_hits_event_bus():
    captured = []
    from app.core import event_bus

    event_bus.register_handler(lambda topic, value: captured.append((topic, value)))
    publish_raw_event(
        {
            "tenant_id": "t1",
            "source_type": "google_gmail",
            "source_instance_id": "c1",
            "source_object_id": "msg-1",
            "object_kind": "message",
            "raw_payload": {"id": "msg-1"},
            "raw_acls": [],
            "identity_refs": [],
            "ingestion_timestamp": "2026-08-18T00:00:00+00:00",
        }
    )
    assert captured
    assert captured[-1][0] == "ingest.raw.v1"
    assert captured[-1][1]["source_object_id"] == "msg-1"


@pytest.mark.asyncio
async def test_oauth_callback_enqueues_drive_and_gmail_backfill(monkeypatch):
    from unittest.mock import AsyncMock

    from app.core.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "google_client_id", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "not-a-real-secret")
    monkeypatch.setattr(
        settings,
        "google_redirect_uri",
        "http://localhost:8000/connectors/google/callback",
    )

    tenant_id = str(uuid4())
    user_id = str(uuid4())
    jti = str(uuid4())
    binding_token = "test-binding-token-123"
    
    # Mock Redis for state encoding
    mock_redis = MagicMock()
    with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
        state = encode_oauth_state(tenant_id, user_id, jti=jti, binding_token=binding_token)

    client = TestClient(app)
    manager = MagicMock()
    manager.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "x", "refresh_token": "y"}
    )
    
    # Mock Redis for state decoding in callback
    mock_redis.get.return_value = json.dumps({
        "nonce": "test-nonce",
        "jti": jti,
        "connection_scope": "personal",
        "binding_token": binding_token
    })
    
    with patch("app.connectors.router.google_oauth_from_settings", return_value=manager), \
         patch("app.connectors.router.backfill_source.delay") as mock_delay, \
         patch("app.connectors.router._record_connector_rows", new=AsyncMock(return_value=None)), \
         patch("app.connectors.router._resolve_mailbox_email", new=AsyncMock(return_value="user@example.com")), \
         patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
        mock_delay.return_value = MagicMock(id="task-1")
        response = client.get(
            "/connectors/google/callback",
            params={"code": "test-code", "state": state},
            cookies={"oauth_binding": binding_token},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert mock_delay.call_count == 2
    sources = {c.kwargs["source_type"] for c in mock_delay.call_args_list}
    assert sources == {"google_drive", "google_gmail"}
    for call in mock_delay.call_args_list:
        assert call.kwargs["tenant_id"] == tenant_id
        assert call.kwargs["user_id"] == user_id
