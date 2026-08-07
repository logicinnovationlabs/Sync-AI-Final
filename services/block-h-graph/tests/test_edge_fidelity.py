"""H1: Edge fidelity — relationship-type counts match graph_edges.json."""

from __future__ import annotations


import pytest


@pytest.mark.asyncio
async def test_h1_edge_fidelity(loaded_store, graph_edges):
    """
    Load graph_edges.json into the graph store and compare counts of each
    relationship type against the fixture expected_counts.

    Pass threshold: 100% match — no missing/extra edges.
    """
    tenant_id = graph_edges["tenant_id"]
    expected = graph_edges["expected_counts"]
    actual = await loaded_store.count_edges_by_type(tenant_id)

    # Normalize keys / ensure all expected types present
    missing = {k: expected[k] for k in expected if actual.get(k, 0) != expected[k]}
    extra = {k: actual[k] for k in actual if k not in expected}

    print("H1 expected:", dict(sorted(expected.items())))
    print("H1 actual:  ", dict(sorted(actual.items())))
    print("H1 total expected:", graph_edges["total_edges"], "actual:", sum(actual.values()))

    assert not missing, f"Count mismatches: {missing}"
    assert not extra, f"Unexpected relationship types: {extra}"
    assert sum(actual.values()) == graph_edges["total_edges"]
    print("H1 Edge fidelity: PASS (100% match)")
