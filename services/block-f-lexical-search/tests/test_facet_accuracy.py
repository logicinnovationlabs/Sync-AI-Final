"""F4 — Facet accuracy 100% match against ground truth."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"


@pytest.mark.asyncio
async def test_F4_facet_accuracy(loaded_store, facet_truth):
    """
    F4 Signoff: facet counts must 100% match Block Z ground truth.
    """
    fields = list(facet_truth["facets"].keys())
    result = await loaded_store.search(
        tenant_id=facet_truth["tenant_id"],
        query=facet_truth.get("query") or "",
        acl_terms=facet_truth["acl_filter_terms"],
        facets=fields,
        size=1,
    )

    actual = result["facets"]
    expected = facet_truth["facets"]
    comparison = {}
    mismatches = []

    for field in fields:
        exp_map = {b["value"]: b["count"] for b in expected.get(field, [])}
        act_map = {b["value"]: b["count"] for b in actual.get(field, [])}
        comparison[field] = {"expected": exp_map, "actual": act_map}
        if exp_map != act_map:
            mismatches.append(field)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "facet_comparison.json").write_text(
        json.dumps(
            {
                "mismatches": mismatches,
                "comparison": comparison,
                "visible_total": result["total"],
                "expected_visible": facet_truth.get("visible_document_count"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nF4 facet fields checked: {fields}")
    print(f"F4 mismatches: {mismatches or 'none'}")
    assert not mismatches, f"F4 FAIL: facet mismatch on {mismatches}"
    print("F4 facet accuracy: 100% match — PASS")