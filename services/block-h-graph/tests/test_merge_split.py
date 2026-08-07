"""H3: Merge/split integrity — no orphaned edges after Person merge."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_h3_merge_split_integrity(loaded_store, graph_edges):
    """
    Merge two Person nodes from the fixture. Query for all edges where start or
    end is the old (secondary) node — they should be 0. After split/restore,
    edges should be correct again with no orphans/dupes.
    """
    tenant_id = graph_edges["tenant_id"]
    candidates = graph_edges["merge_candidates"]
    primary = candidates["primary_id"]
    secondary = candidates["secondary_id"]

    before_secondary = await loaded_store.get_edges_involving(tenant_id, secondary)
    assert len(before_secondary) > 0, "Fixture secondary must have edges to merge"

    before_counts = await loaded_store.count_edges_by_type(tenant_id)
    before_total = sum(before_counts.values())

    merge_result = await loaded_store.merge_persons(tenant_id, primary, secondary)
    assert merge_result["secondary_deleted"] is True
    assert merge_result["edges_redirected"] >= len(before_secondary)

    # H3 core: zero edges involving the old secondary node
    after_secondary = await loaded_store.get_edges_involving(tenant_id, secondary)
    assert after_secondary == [], f"Orphaned edges remain on secondary: {after_secondary}"

    # Secondary node gone
    people = await loaded_store.people_search(tenant_id, query="Alice", limit=50)
    ids = {p["id"] for p in people}
    assert secondary not in ids
    assert primary in ids

    # No duplicate identical edges after merge
    after_counts = await loaded_store.count_edges_by_type(tenant_id)
    after_edges_primary = await loaded_store.get_edges_involving(tenant_id, primary)
    keys = [(e["type"], e["source_id"], e["target_id"]) for e in after_edges_primary]
    assert len(keys) == len(set(keys)), "Duplicated edges after merge"

    # Split / restore from snapshot
    snapshot = merge_result.get("snapshot")
    split_result = await loaded_store.split_persons(
        tenant_id, primary, secondary, snapshot=snapshot
    )
    assert split_result.get("restored") is True

    restored_secondary = await loaded_store.get_edges_involving(tenant_id, secondary)
    assert len(restored_secondary) == len(before_secondary), (
        f"After split expected {len(before_secondary)} edges on secondary, "
        f"got {len(restored_secondary)}"
    )

    restored_counts = await loaded_store.count_edges_by_type(tenant_id)
    assert sum(restored_counts.values()) == before_total, (
        f"Edge total drift after split: before={before_total} "
        f"after={sum(restored_counts.values())} counts={restored_counts}"
    )

    print(
        f"H3 merge redirected={merge_result['edges_redirected']} "
        f"orphans_after_merge=0 restored_edges={len(restored_secondary)}"
    )
    print("H3 Merge/split integrity: PASS")
