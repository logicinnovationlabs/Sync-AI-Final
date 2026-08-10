"""I1 — Privacy threshold enforcement (Block Z privacy_test_cases.json)."""

from __future__ import annotations

import os

import json
from pathlib import Path

import pytest

from tests.conftest import auth_headers

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
PHASE_SUFFIX = "_phase2" if os.environ.get("SIGNALS_BACKEND", "mock").lower() == "postgres" else ""


@pytest.mark.asyncio
async def test_i1_privacy_threshold(client, store, privacy_cases):
    """
    For actor counts < threshold: privacy_protected=true, null signals.
    For >= threshold: numeric popularity returned.
    No successful inference of individual actors from protected cases.
    """
    results = []
    for case in privacy_cases["cases"]:
        tenant = case["tenant_id"]
        headers = auth_headers(tenant)
        from app.models.activity import ActivityConfig

        await store.set_config(
            ActivityConfig(
                tenant_id=tenant,
                privacy_threshold=case["privacy_threshold"],
            )
        )
        body = {"events": case["events"]}
        resp = await client.post("/activity/ingest", json=body, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["ingested_count"] == len(case["events"])

        sig = await client.get(
            f"/signals/document/{case['document_id']}", headers=headers
        )
        assert sig.status_code == 200, sig.text
        data = sig.json()
        entry = {
            "case_id": case["case_id"],
            "distinct_actor_count": case["distinct_actor_count"],
            "expect_privacy_protected": case["expect_privacy_protected"],
            "response": data,
        }
        results.append(entry)

        if case["expect_privacy_protected"]:
            assert data["privacy_protected"] is True
            assert data["popularity_score"] is None
            assert data["total_views"] is None
            assert data["distinct_viewers"] is None
            assert data["last_viewed"] is None
            blob = json.dumps(data)
            for ev in case["events"]:
                assert ev["actor_principal_id"] not in blob
        else:
            assert data["privacy_protected"] is False
            assert data["popularity_score"] is not None
            assert data["total_views"] is not None and data["total_views"] >= 1
            assert data["distinct_viewers"] == case["distinct_actor_count"]

    EVIDENCE.mkdir(exist_ok=True)
    out = EVIDENCE / f"i1_privacy_report{PHASE_SUFFIX}.json"
    out.write_text(json.dumps({"passed": True, "cases": results}, indent=2, default=str), encoding="utf-8")
    print(f"I1 PASS — {len(results)} privacy cases; report={out}")