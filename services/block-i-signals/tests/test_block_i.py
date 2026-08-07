"""Additional Block I checks: idempotency, tenant isolation, basic API contract."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.conftest import auth_headers


def _view_event(event_id: str, actor: str, doc: str) -> dict:
    return {
        "event_id": event_id,
        "actor_principal_id": actor,
        "object_id": doc,
        "event_type": "view",
        "source_system": "confluence",
        "event_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "privacy_level": "public",
    }


@pytest.mark.asyncio
async def test_idempotent_reingest(client, store):
    headers = auth_headers("tenant-a")
    # Seed 5 distinct actors so signal is visible
    seeds = [_view_event(f"idem-seed-{i}", f"p-idem-{i}", "doc-idem-001") for i in range(5)]
    await client.post("/activity/ingest", json={"events": seeds}, headers=headers)

    evt = _view_event("idem-evt-001", "p-idem-0", "doc-idem-001")
    r1 = await client.post("/activity/ingest", json={"events": [evt]}, headers=headers)
    assert r1.status_code == 200
    assert r1.json()["ingested_count"] == 1

    before = (await client.get("/signals/document/doc-idem-001", headers=headers)).json()

    r2 = await client.post("/activity/ingest", json={"events": [evt]}, headers=headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["ingested_count"] == 0
    assert body["already_processed_count"] == 1

    after = (await client.get("/signals/document/doc-idem-001", headers=headers)).json()
    assert after["total_views"] == before["total_views"]
    assert after["distinct_viewers"] == before["distinct_viewers"]


@pytest.mark.asyncio
async def test_tenant_isolation(client, store):
    """Tenant B must not see tenant A document signals (empty/protected isolation)."""
    headers_a = auth_headers("tenant-iso-a", "p-a")
    headers_b = auth_headers("tenant-iso-b", "p-b")

    # Put 6 viewers in tenant A so signal is numeric
    events = [
        _view_event(f"iso-a-{i}", f"p-a-{i}", "doc-shared-name") for i in range(6)
    ]
    r = await client.post("/activity/ingest", json={"events": events}, headers=headers_a)
    assert r.status_code == 200
    assert r.json()["ingested_count"] == 6

    sig_a = (await client.get("/signals/document/doc-shared-name", headers=headers_a)).json()
    assert sig_a["privacy_protected"] is False
    assert sig_a["distinct_viewers"] == 6
    assert sig_a["tenant_id"] == "tenant-iso-a"

    # Same document_id in tenant B has no events → privacy protected / null
    sig_b = (await client.get("/signals/document/doc-shared-name", headers=headers_b)).json()
    assert sig_b["tenant_id"] == "tenant-iso-b"
    assert sig_b["privacy_protected"] is True
    assert sig_b["total_views"] is None
    assert sig_b["distinct_viewers"] is None

    # Body tenant_id mismatch rejected
    bad = _view_event("iso-mismatch", "p-a-0", "doc-x")
    bad["tenant_id"] = "tenant-iso-b"
    rbad = await client.post("/activity/ingest", json={"events": [bad]}, headers=headers_a)
    assert rbad.status_code == 200
    assert rbad.json()["failed_events"]
    assert rbad.json()["ingested_count"] == 0


@pytest.mark.asyncio
async def test_missing_scope_rejected(client):
    headers = auth_headers("tenant-a", scopes=["search.read"])
    r = await client.post(
        "/activity/ingest",
        json={"events": [_view_event("noscope", "p-x", "doc-x")]},
        headers=headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "block-i-signals"
