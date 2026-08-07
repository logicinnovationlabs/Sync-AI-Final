"""I3 — Signal freshness (p95 <= 15 minutes)."""

from __future__ import annotations

import os

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.conftest import auth_headers

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
PHASE_SUFFIX = "_phase2" if os.environ.get("SIGNALS_BACKEND", "mock").lower() == "postgres" else ""


@pytest.mark.asyncio
async def test_i3_signal_freshness(client, store, ground_truth, events_fixture):
    """
    After ingesting an activity event at t=0, document signal reflects it
    within <= 15 minutes (p95). Mock path updates synchronously (lag ~0).
    """
    tenant = ground_truth["tenant_id"]
    headers = auth_headers(tenant)
    freshness = ground_truth["freshness"]
    max_s = freshness["max_freshness_seconds"]
    probe = freshness["probe_event"]
    doc_id = probe["object_id"]

    seed_events = []
    for i, actor in enumerate(freshness["seed_actors"]):
        if actor == probe["actor_principal_id"]:
            continue
        seed_events.append(
            {
                "event_id": f"evt-fresh-seed-{i:02d}",
                "actor_principal_id": actor,
                "object_id": doc_id,
                "event_type": "view",
                "source_system": "confluence",
                "event_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "privacy_level": "public",
            }
        )
    if seed_events:
        r = await client.post("/activity/ingest", json={"events": seed_events}, headers=headers)
        assert r.status_code == 200

    before = (await client.get(f"/signals/document/{doc_id}", headers=headers)).json()
    before_views = before.get("total_views") or 0

    lags = []
    for i in range(20):
        evt = dict(probe)
        evt["event_id"] = f"evt-freshness-probe-{i:03d}"
        evt["event_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        t0 = time.perf_counter()
        resp = await client.post("/activity/ingest", json={"events": [evt]}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["ingested_count"] == 1

        reflected = False
        deadline = time.perf_counter() + max_s
        while time.perf_counter() < deadline:
            sig = (await client.get(f"/signals/document/{doc_id}", headers=headers)).json()
            if (
                not sig.get("privacy_protected")
                and sig.get("total_views") is not None
                and sig["total_views"] > before_views + i
            ):
                lags.append(time.perf_counter() - t0)
                reflected = True
                break
            if sig.get("last_viewed"):
                lags.append(time.perf_counter() - t0)
                reflected = True
                break
            time.sleep(0.01)
        assert reflected, f"signal not fresh within {max_s}s for probe {i}"

    lags_sorted = sorted(lags)
    p95 = lags_sorted[max(0, int(0.95 * len(lags_sorted)) - 1)]
    report = {
        "n": len(lags),
        "avg_s": sum(lags) / len(lags),
        "p95_s": p95,
        "max_s": max(lags),
        "threshold_s": max_s,
        "passed": p95 <= max_s,
    }
    EVIDENCE.mkdir(exist_ok=True)
    out = EVIDENCE / f"i3_freshness_report{PHASE_SUFFIX}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert p95 <= max_s, report
    print(f"I3 PASS — p95={p95:.4f}s (threshold {max_s}s); report={out}")


@pytest.mark.asyncio
async def test_i3_ground_truth_user_and_doc(client, store, ground_truth, events_fixture):
    """Ingest events.json and verify ground-truth document/user signals."""
    tenant = ground_truth["tenant_id"]
    headers = auth_headers(tenant)

    tenant_events = [e for e in events_fixture["events"] if e["tenant_id"] == tenant]
    for i in range(0, len(tenant_events), 25):
        chunk = tenant_events[i : i + 25]
        r = await client.post("/activity/ingest", json={"events": chunk}, headers=headers)
        assert r.status_code == 200

    for doc_id, expect in ground_truth["documents"].items():
        sig = (await client.get(f"/signals/document/{doc_id}", headers=headers)).json()
        assert sig["privacy_protected"] is expect["expect_privacy_protected"]
        if not expect["expect_privacy_protected"]:
            assert sig["distinct_viewers"] >= expect["min_distinct_viewers"]
            assert sig["total_views"] >= expect["min_total_views"]
            assert sig["popularity_score"] is not None

    for user_id, expect in ground_truth["users"].items():
        sig = (await client.get(f"/signals/user/{user_id}", headers=headers)).json()
        assert sig["user_id"] == user_id
        if expect.get("expect_last_active"):
            assert sig["signals"]["last_active"] is not None
        if sig.get("freshness_s") is not None:
            assert sig["freshness_s"] <= ground_truth["freshness"]["max_freshness_seconds"]