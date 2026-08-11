"""K2 — Streaming for documents >10MB; memory stays bounded."""

from __future__ import annotations

import tracemalloc

import pytest

from tests.conftest import make_bearer

TENANT = "tenant-k"
DOC_ID = "doc-large-k2"
USER_A = "user-a"
LARGE_SIZE = 10 * 1024 * 1024 + 64 * 1024


@pytest.mark.asyncio
async def test_k2_streams_large_document(k_app):
    client, store, acl, _app = k_app

    from app.config import settings
    from app.services.document_reader import stream_document_json

    prev_threshold = settings.stream_threshold_bytes
    settings.stream_threshold_bytes = 10 * 1024 * 1024

    body = ("A" * 1024) * (LARGE_SIZE // 1024)
    assert len(body) > 10 * 1024 * 1024

    meta = store.upsert(
        TENANT,
        DOC_ID,
        title="Large Streaming Doc",
        body=body,
        owner_principal_id=USER_A,
        created_at="2026-08-10T12:00:00Z",
        updated_at="2026-08-11T10:00:00Z",
        structured_metadata={
            "headings": ["Huge"],
            "tables": [],
            "code_blocks": [],
            "language": "en",
        },
    )
    acl.grant(TENANT, DOC_ID, USER_A)

    resp = await client.get(
        f"/api/v1/document/{DOC_ID}",
        headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("x-document-streaming") == "1"
    assert resp.headers.get("content-type", "").startswith("application/json")

    data = resp.json()
    assert data["document_id"] == DOC_ID
    assert data["title"] == "Large Streaming Doc"
    assert len(data["body"]) == len(body)
    assert data["body"].startswith("AAAA")
    assert data["body"].endswith("AAAA")

    # Generator memory stays bounded when chunks are not retained
    tracemalloc.start()
    baseline = tracemalloc.get_traced_memory()[0]
    total = 0
    peak_seen = 0
    async for chunk in stream_document_json(
        store,
        meta["object_key"],
        DOC_ID,
        TENANT,
        {
            "title": meta["title"],
            "owner_principal_id": USER_A,
            "created_at": meta["created_at"],
            "updated_at": meta["updated_at"],
        },
        meta["structured_metadata"],
    ):
        total += len(chunk)
        _current, peak = tracemalloc.get_traced_memory()
        peak_seen = max(peak_seen, peak)

    growth = peak_seen - baseline
    tracemalloc.stop()
    settings.stream_threshold_bytes = prev_threshold

    assert total > len(body), "stream should emit metadata + body"
    assert growth < 5 * 1024 * 1024, (
        f"Stream generator peak growth {growth} not bounded "
        f"(want <5MB while streaming {len(body)}-byte body)"
    )


@pytest.mark.asyncio
async def test_k2_small_document_not_streamed(k_app):
    client, store, acl, _app = k_app
    store.upsert(
        TENANT,
        "doc-small",
        title="Small",
        body="hello world",
        owner_principal_id=USER_A,
    )
    acl.grant(TENANT, "doc-small", USER_A)

    resp = await client.get(
        "/api/v1/document/doc-small",
        headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("x-document-streaming") is None
    assert resp.json()["body"] == "hello world"