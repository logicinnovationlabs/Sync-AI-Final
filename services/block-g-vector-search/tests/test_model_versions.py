"""G4 — Model-version handling (no cross-model score mixing)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_G4_model_version_filter(mixed_version_store, corpus, relevance):
    """
    G4 Signoff:
    - Query with model_version=v2 returns only v2
    - Query without filter may return both, each tagged
    - Scores from different versions must not be treated as comparable
    """
    tenant_id = corpus["tenant_id"]
    v1, v2 = corpus["model_versions"]
    q = relevance["queries"][0]

    # Filtered to v2 only
    v2_results = await mixed_version_store.search(
        tenant_id=tenant_id,
        query_embedding=q["query_embedding"],
        acl_terms=q["acl_filter_terms"],
        top_k=20,
        model_version=v2,
    )
    assert v2_results, "Expected v2 results"
    assert all(r["model_version"] == v2 for r in v2_results), "Non-v2 result when filtered"
    print(f"  filtered v2: {len(v2_results)} results, all tagged {v2}")

    # Filtered to v1 only
    v1_results = await mixed_version_store.search(
        tenant_id=tenant_id,
        query_embedding=q["query_embedding"],
        acl_terms=q["acl_filter_terms"],
        top_k=20,
        model_version=v1,
    )
    assert v1_results, "Expected v1 results"
    assert all(r["model_version"] == v1 for r in v1_results)
    print(f"  filtered v1: {len(v1_results)} results, all tagged {v1}")

    # Unfiltered — both versions allowed, every result tagged
    mixed = await mixed_version_store.search(
        tenant_id=tenant_id,
        query_embedding=q["query_embedding"],
        acl_terms=q["acl_filter_terms"],
        top_k=40,
        model_version=None,
    )
    assert mixed, "Expected mixed results"
    versions = {r["model_version"] for r in mixed}
    assert all(r.get("model_version") for r in mixed), "Every result must include model_version"
    assert versions <= {v1, v2}
    print(f"  unfiltered: {len(mixed)} results, versions={sorted(versions)}")

    # No cross-model score mixing contract:
    # Within each version group, scores must be monotonically non-increasing
    # when listed in the order returned for that version.
    for ver in versions:
        group = [r for r in mixed if r["model_version"] == ver]
        scores = [r["score"] for r in group]
        assert scores == sorted(scores, reverse=True), (
            f"Scores for {ver} are not ranked independently (cross-model mixing suspected)"
        )

    # Callers must not compare scores across versions — enforce by checking
    # that the API/store always emits model_version and that a naive global
    # sort is not claimed comparable: we only assert tagging + per-version order.
    print("\nG4 model-version handling: PASS (tagged, filtered, no cross-model ranking claim)")