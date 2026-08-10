"""F2 — ACL enforcement: 0 unauthorized results across 15 red-team cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"


@pytest.mark.asyncio
async def test_F2_acl_redteam_zero_unauthorized(loaded_store, redteam):
    """
    F2 Signoff: Block Z's fixed 15-case red-team list.
    PASS: 0 unauthorized results across all 15 cases.
    """
    cases = redteam["cases"]
    assert len(cases) == 15, "Block Z ACL red-team set must contain 15 cases"

    report = []
    leaks = []

    for case in cases:
        result = await loaded_store.search(
            tenant_id=case["tenant_id"],
            query=case["query"],
            acl_terms=case.get("acl_filter_terms") or [],
            size=case.get("top_k", 50),
        )
        returned_ids = {r["document_id"] for r in result["results"]}
        forbidden = set(case.get("forbidden_document_ids") or [])
        leaked = sorted(returned_ids & forbidden)

        if case.get("expect_total_zero"):
            if result["total"] != 0 or returned_ids:
                leaks.append((case["case_id"], ["non-empty-unauthenticated-result"]))
                leaked = sorted(returned_ids) or ["non-empty"]

        must_include = set(case.get("must_include_document_ids") or [])
        missing = sorted(must_include - returned_ids)

        entry = {
            "case_id": case["case_id"],
            "description": case.get("description"),
            "returned": len(result["results"]),
            "total": result["total"],
            "leaked": leaked,
            "missing_required": missing,
        }
        report.append(entry)
        print(
            f"  {case['case_id']}: returned={entry['returned']} "
            f"leaked={leaked} missing={missing}"
        )
        if leaked:
            leaks.append((case["case_id"], leaked))
        if missing:
            leaks.append((case["case_id"], [f"missing:{m}" for m in missing]))

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "redteam_report.json").write_text(
        json.dumps({"cases": report, "leaks": leaks}, indent=2),
        encoding="utf-8",
    )

    assert not leaks, f"F2 FAIL: unauthorized/missing results: {leaks}"
    print("\nF2 ACL enforcement: 0 unauthorized across 15 cases — PASS")