"""I2 — Retention enforcement (Block Z retention_test_cases.json)."""

from __future__ import annotations

import os

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.activity import ActivityEvent
from tests.conftest import auth_headers

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
PHASE_SUFFIX = "_phase2" if os.environ.get("SIGNALS_BACKEND", "mock").lower() == "postgres" else ""


@pytest.mark.asyncio
async def test_i2_retention_enforcement(client, store, retention_cases):
    """
    100% of expired records purged. No record with ingested_at < NOW()-TTL remains.
    Uses short TTLs from fixtures so the test does not wait hours.
    """
    tenant = "tenant-a"
    headers = auth_headers(tenant)
    now = datetime.now(timezone.utc)

    for case in retention_cases["cases"]:
        event = ActivityEvent.model_validate(
            {k: v for k, v in case.items() if k not in ("ingested_at_offset_seconds", "expect_purged")}
        )
        offset = int(case.get("ingested_at_offset_seconds") or 0)
        ingested_at = now + timedelta(seconds=offset)
        result = await store.ingest_event(tenant, event, ingested_at=ingested_at)
        assert result == "ingested"

    before = await store.list_events(tenant, include_expired=True)
    before_ids = {e.event_id for e in before}
    for case in retention_cases["cases"]:
        assert case["event_id"] in before_ids

    purge = await store.purge_expired(now=now)
    after = await store.list_events(tenant, include_expired=True)
    after_ids = {e.event_id for e in after}

    expired_expected = [c["event_id"] for c in retention_cases["cases"] if c["expect_purged"]]
    active_expected = [c["event_id"] for c in retention_cases["cases"] if not c["expect_purged"]]

    missing_purge = [eid for eid in expired_expected if eid in after_ids]
    missing_active = [eid for eid in active_expected if eid not in after_ids]

    still_expired = []
    for ev in after:
        expiry = ev.ingested_at + timedelta(seconds=ev.ttl_seconds)
        if now >= expiry:
            still_expired.append(ev.event_id)

    report = {
        "purged_events": purge.purged_events,
        "expired_expected": expired_expected,
        "active_expected": active_expected,
        "missing_purge": missing_purge,
        "missing_active": missing_active,
        "still_expired": still_expired,
        "after_count": len(after),
    }
    EVIDENCE.mkdir(exist_ok=True)
    out = EVIDENCE / f"i2_retention_report{PHASE_SUFFIX}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    assert not missing_purge, f"expired not purged: {missing_purge}"
    assert not missing_active, f"active wrongly purged: {missing_active}"
    assert not still_expired, f"TTL-expired remain: {still_expired}"
    assert purge.purged_events >= len(expired_expected)

    sig = await client.get("/signals/document/doc-ret-expired", headers=headers)
    assert sig.status_code == 200
    data = sig.json()
    assert data["privacy_protected"] is True or (data.get("total_views") in (None, 0))

    print(f"I2 PASS — purged={purge.purged_events}; report={out}")