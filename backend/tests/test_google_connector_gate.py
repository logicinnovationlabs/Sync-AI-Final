"""
Gate tests: Block C path visibility, and seed_token_store_from_env must not clobber.

Never prints live secret values.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "google"


@pytest.mark.asyncio
async def test_process_raw_batch_drive_fixture_uses_block_c(caplog):
    """Real Drive fixture through process_raw_batch — which path fires?"""
    from app.connectors.google.pipeline_bridge import process_raw_batch

    page = json.loads((FIXTURES / "drive" / "backfill_page1.json").read_text(encoding="utf-8"))
    files = page["files"]
    for f in files:
        f.setdefault("_extracted_text", f.get("name", "fixture text"))
        f.setdefault("_test_detected_mime", f.get("mimeType", "text/plain"))

    tenant_id = str(uuid4())
    with caplog.at_level(logging.INFO):
        result = await process_raw_batch(files, "google_drive", tenant_id)

    records = " | ".join(r.message for r in caplog.records)
    assert result is not None, f"Block C returned None. logs={records}"
    assert len(result) >= 1
    assert any("pipeline=block_c" in r.message for r in caplog.records), records
    assert not any(
        "pipeline=fallback_transform" in r.message for r in caplog.records
    ), records
    # Permissions must be resolved user:/group: prefixes (Block C ACL compile)
    assert all(
        p.startswith("user:") or p.startswith("group:")
        for doc in result
        for p in doc.permissions
    )


@pytest.mark.asyncio
async def test_process_raw_batch_gmail_fixture_uses_block_c(caplog):
    from app.connectors.google.pipeline_bridge import process_raw_batch

    page = json.loads((FIXTURES / "gmail" / "backfill_page1.json").read_text(encoding="utf-8"))
    messages = page["full_messages"]
    for m in messages:
        m.setdefault("_mailbox_email", "mailbox@example.com")
        m.setdefault("_test_extracted_text", m.get("snippet", "email body"))

    tenant_id = str(uuid4())
    with caplog.at_level(logging.INFO):
        result = await process_raw_batch(messages, "google_gmail", tenant_id)

    records = " | ".join(r.message for r in caplog.records)
    assert result is not None, f"Block C returned None. logs={records}"
    assert len(result) >= 1
    assert any("pipeline=block_c" in r.message for r in caplog.records), records


def test_seed_does_not_clobber_existing_token(monkeypatch):
    """GOOGLE_REFRESH_TOKEN must not overwrite a token already stored for the tenant."""
    from app.connectors.google.oauth import seed_token_store_from_env

    class Store:
        def __init__(self):
            self._t = {}

        def get_token(self, key):
            return self._t.get(key)

        def set_token(self, key, token_data):
            self._t[key] = dict(token_data)

    tenant_id = str(uuid4())
    store = Store()
    original = {
        "access_token": "real-oauth-access-sentinel",
        "refresh_token": "real-oauth-refresh-sentinel",
        "token_type": "Bearer",
    }
    store.set_token(f"google_oauth:{tenant_id}", original)
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "env-refresh-token-must-not-win")

    seeded = seed_token_store_from_env(
        store,
        tenant_id,
        refresh_token="env-refresh-token-must-not-win",
    )
    assert seeded is False
    kept = store.get_token(f"google_oauth:{tenant_id}")
    assert kept["access_token"] == "real-oauth-access-sentinel"
    assert kept["refresh_token"] == "real-oauth-refresh-sentinel"


def test_backfill_path_does_not_clobber_stored_token(monkeypatch):
    """Full backfill entry calls seed_token_store_from_env; stored OAuth token must survive."""
    from app.workers.tasks import DummyTokenStore, backfill_tenant_source

    tenant_id = str(uuid4())
    original = {
        "access_token": "real-oauth-access-sentinel",
        "refresh_token": "real-oauth-refresh-sentinel",
        "token_type": "Bearer",
    }

    # PersistentGoogleTokenStore in the task: intercept get/set via a shared DummyTokenStore
    sentinel_store = DummyTokenStore()
    sentinel_store.set_token(f"google_oauth:{tenant_id}", original)

    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "env-refresh-token-must-not-win")
    monkeypatch.setattr(
        "app.core.config.settings.google_refresh_token",
        "env-refresh-token-must-not-win",
        raising=False,
    )

    class _BoundStore:
        """Stand-in that starts with the real token already stored."""

        def __init__(self, tenant_id_arg=None):
            self.tenant_id = tenant_id_arg or tenant_id

        def get_token(self, key):
            return sentinel_store.get_token(key)

        def set_token(self, key, token_data):
            sentinel_store.set_token(key, token_data)

        def bind_tenant(self, tid):
            self.tenant_id = tid
            return self

    with patch("app.workers.tasks.PersistentGoogleTokenStore", _BoundStore), patch(
        "app.workers.tasks.sync_orchestrator.run_two_pass_sync",
        return_value={"indexed_count": 0, "deleted_count": 0, "final_cursor": None, "pages_processed": 0},
    ), patch(
        "app.workers.tasks.cursor_store.get_cursor",
        new_callable=MagicMock,
    ) as mock_get_cursor, patch(
        "app.workers.tasks.cursor_store.update_cursor",
        new_callable=MagicMock,
    ), patch(
        "app.workers.tasks.WatchManager",
    ), patch(
        "app.workers.tasks.connector_registry.get_connector",
        return_value=MagicMock(oauth_manager=None),
    ):
        mock_get_cursor.return_value = None
        # get_cursor is awaited via _run_async; make it a coroutine
        async def _none(*_a, **_k):
            return None

        mock_get_cursor.side_effect = lambda *a, **k: _none()

        backfill_tenant_source(tenant_id=tenant_id, source_type="google_drive")

    kept = sentinel_store.get_token(f"google_oauth:{tenant_id}")
    assert kept is not None
    assert kept["access_token"] == "real-oauth-access-sentinel"
    assert kept["refresh_token"] == "real-oauth-refresh-sentinel"
    assert "env-refresh-token-must-not-win" not in (kept["refresh_token"], kept["access_token"])
