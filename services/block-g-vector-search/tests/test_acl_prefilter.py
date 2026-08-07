"""G2 — ACL prefilter zero-leak red-team."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_G2_acl_prefilter_zero_leak(loaded_store, redteam):
    """
    G2 Signoff: 15 red-team cases must return 0 restricted chunks.
    """
    cases = redteam["cases"]
    assert len(cases) == 15, "Block Z ACL red-team set must contain 15 cases"

    leaks = []
    for case in cases:
        results = await loaded_store.search(
            tenant_id=case["tenant_id"],
            query_embedding=case["query_embedding"],
            acl_terms=case["acl_filter_terms"],
            top_k=case.get("top_k", 50),
            model_version=case.get("model_version"),
        )
        returned = {r["chunk_id"] for r in results}
        forbidden = set(case["forbidden_chunk_ids"])
        leaked = sorted(returned & forbidden)
        print(
            f"  {case['case_id']}: returned={len(results)} leaked={leaked}"
        )
        if leaked:
            leaks.append((case["case_id"], leaked))

    assert not leaks, f"G2 FAIL: restricted chunks leaked: {leaks}"
    print("\nG2 ACL prefilter: 0 restricted chunks across 15 cases — PASS")