"""
B5 Phase 2 — Checkpoint resume against real Google Gmail (Drive fallback).

Credential path (Block B actual pattern):
  - CLIENT_ID/SECRET: settings/env (google_client_id / GOOGLE_CLIENT_ID)
  - User tokens: TokenStore key ``google_oauth:{tenant_id}`` via GoogleOAuthManager
  - GOOGLE_REFRESH_TOKEN seeds TokenStore via seed_token_store_from_env()

Never prints refresh/access token values.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)


def _creds_present() -> bool:
    return all(
        os.getenv(k)
        for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    )


class _KillAfterCheckpoint(Exception):
    pass


class _MemTokenStore:
    def __init__(self):
        self._t: Dict[str, Any] = {}

    def get_token(self, key: str):
        return self._t.get(key)

    def set_token(self, key: str, token_data: dict) -> None:
        self._t[key] = token_data


def _sync_refresh_and_seed(store: _MemTokenStore, tenant_id: str) -> int:
    """Exchange refresh token synchronously; seed TokenStore. Returns access_token length."""
    cid = os.environ["GOOGLE_CLIENT_ID"]
    secret = os.environ["GOOGLE_CLIENT_SECRET"]
    rt = os.environ["GOOGLE_REFRESH_TOKEN"]
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": cid,
                "client_secret": secret,
                "refresh_token": rt,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        body = resp.text.replace(rt, "[REDACTED_REFRESH]")
        raise AssertionError(f"token refresh HTTP {resp.status_code}: {body[:400]}")
    data = resp.json()
    access = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    store.set_token(
        f"google_oauth:{tenant_id}",
        {
            "access_token": access,
            "refresh_token": rt,
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 120))
            )
            .replace(tzinfo=None)
            .isoformat(),
            "token_type": "Bearer",
        },
    )
    return len(access)


@pytest.mark.skipif(not _creds_present(), reason="GOOGLE_* including REFRESH_TOKEN required")
def test_b5_checkpoint_resume_real_gmail():
    """
    Real-source B5 against Gmail (multi-page). Drive account currently has too few
    files for a multi-page kill; smoke confirmed Drive auth works separately.

    Proves pagination / checkpoint-resume against live Gmail, not ACL persist.
    process_raw_batch is mocked to return None so indexing uses
    connector.transform — do not rely on an unrouted tenant id to
    silently skip Block C.
    """
    from app.connectors.google.oauth import GoogleOAuthManager, seed_token_store_from_env
    from app.connectors.google.services.gmail_service import GmailConnector
    from app.core.base_connector import DeltaResult
    from app.services.sync import sync_orchestrator

    tenant_id = "tenant-b5-real-gmail"
    page_size = int(os.getenv("B5_REAL_PAGE_SIZE", "2"))

    store = _MemTokenStore()
    # Demonstrate production seed helper also works
    assert seed_token_store_from_env(store, tenant_id) is True
    access_len = _sync_refresh_and_seed(store, tenant_id)
    print(f"[B5-REAL] TokenStore seeded; access_token len={access_len} (value redacted)")

    oauth = GoogleOAuthManager(
        token_store=store,
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/gmail.readonly",
        ],
    )
    connector = GmailConnector(
        {"tenant_id": tenant_id, "mailbox_email": "syncai740@gmail.com"},
        store,
        oauth_manager=oauth,
    )

    async def fetch_delta_paged(since, cursor):
        token = await connector.get_valid_token()
        response = await connector.gmail_client.list_messages(
            access_token=token,
            page_size=page_size,
            page_token=cursor,
        )
        message_ids = [msg["id"] for msg in response.get("messages", [])]
        messages = []
        for msg_id in message_ids:
            try:
                messages.append(await connector.gmail_client.get_message(token, msg_id))
            except Exception:
                continue
        next_page_token = response.get("nextPageToken")
        return DeltaResult(
            documents=messages,
            next_cursor=next_page_token,
            has_more=bool(next_page_token),
        )

    async def fetch_deleted_noop(since, cursor):
        raise NotImplementedError("skip deletions for B5 real checkpoint test")

    connector.fetch_delta = fetch_delta_paged  # type: ignore
    connector.fetch_deleted_ids = fetch_deleted_noop  # type: ignore

    indexed_store: Dict[str, Any] = {}

    async def fake_bulk_index(docs, tenant_id_arg, **kwargs):
        for d in docs:
            indexed_store[d.id] = d

    async def fake_delete_by_ids(ids, tenant_id_arg, source_type):
        for i in ids:
            indexed_store.pop(i, None)

    async def skip_block_c(*args, **kwargs):
        return None

    checkpoint = {"cursor": None, "updates": []}

    def persist_cursor(next_cursor: str):
        checkpoint["cursor"] = next_cursor
        checkpoint["updates"].append(next_cursor)

    since = datetime(1970, 1, 1, tzinfo=timezone.utc)

    with patch(
        "app.connectors.google.pipeline_bridge.process_raw_batch",
        side_effect=skip_block_c,
    ), patch("app.services.sync.indexer") as mock_indexer:
        mock_indexer.bulk_index = fake_bulk_index
        mock_indexer.delete_by_ids = fake_delete_by_ids

        baseline = sync_orchestrator.run_two_pass_sync(
            connector=connector,
            tenant_id=tenant_id,
            since=since,
            cursor=None,
            on_cursor_update=persist_cursor,
        )
        baseline_ids = set(baseline["indexed_ids"])
        pages = baseline["pages_processed"]
        total = baseline["indexed_count"]
        print(
            f"[B5-REAL] Baseline Gmail: pages={pages} objects={total} "
            f"final_cursor={baseline.get('final_cursor')!r}"
        )

        if pages < 2 or total < page_size + 1:
            pytest.skip(
                f"BLOCKED: Gmail pages={pages} objects={total}; need >=2 pages "
                f"(page_size={page_size}). Add more mail or lower B5_REAL_PAGE_SIZE."
            )

        kill_after_pages = max(1, pages // 2)
        indexed_store.clear()
        checkpoint["cursor"] = None
        checkpoint["updates"].clear()
        pages_seen = {"n": 0}

        def persist_and_maybe_kill(next_cursor: str):
            checkpoint["cursor"] = next_cursor
            checkpoint["updates"].append(next_cursor)
            pages_seen["n"] += 1
            if pages_seen["n"] >= kill_after_pages:
                raise _KillAfterCheckpoint(
                    f"simulated kill after page {pages_seen['n']} cursor={next_cursor}"
                )

        with pytest.raises(_KillAfterCheckpoint):
            sync_orchestrator.run_two_pass_sync(
                connector=connector,
                tenant_id=tenant_id,
                since=since,
                cursor=None,
                on_cursor_update=persist_and_maybe_kill,
            )

        partial_ids = set(indexed_store.keys())
        resume_cursor = checkpoint["cursor"]
        assert resume_cursor is not None
        print(
            f"[B5-REAL] Killed after {pages_seen['n']}/{pages} pages; "
            f"partial_objects={len(partial_ids)} checkpoint_cursor={resume_cursor!r}"
        )

        resumed = sync_orchestrator.run_two_pass_sync(
            connector=connector,
            tenant_id=tenant_id,
            since=since,
            cursor=resume_cursor,
            on_cursor_update=persist_cursor,
        )

        final_ids = set(indexed_store.keys())
        assert len(final_ids) == total, f"final {len(final_ids)} != baseline {total}"
        assert final_ids == baseline_ids, "final set drifted from baseline"
        resumed_ids = set(resumed["indexed_ids"])
        assert partial_ids.isdisjoint(resumed_ids), "overlap between kill and resume segments"

        print(
            f"[PASS] B5 Phase 2 real Gmail: kill after {kill_after_pages}/{pages} pages; "
            f"partial={len(partial_ids)} resumed={len(resumed_ids)} "
            f"final={len(final_ids)} matches baseline; 0 dupes/missing"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
