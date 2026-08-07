"""H2: Traversal latency — p95 of 50 depth-2 traversals <= 100 ms."""

from __future__ import annotations

import statistics
import time

import pytest


@pytest.mark.asyncio
async def test_h2_traversal_latency(loaded_store, graph_edges):
    """
    Run 50 depth-2 traversal queries against the populated graph, each with a
    different starting node. Measure p95 latency over the 50 runs.

    Pass threshold: p95 <= 100 ms.
    """
    tenant_id = graph_edges["tenant_id"]
    node_ids = await loaded_store.list_node_ids(tenant_id)
    assert len(node_ids) >= 50, f"Need >=50 nodes for H2, got {len(node_ids)}"

    # Deterministic sample of 50 distinct start nodes
    starts = sorted(node_ids)[:50]
    latencies_ms = []

    for start in starts:
        t0 = time.perf_counter()
        result = await loaded_store.traverse(
            tenant_id=tenant_id,
            start_node_id=start,
            relationship_types=None,
            depth=2,
            limit=100,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)
        assert "nodes" in result and "relationships" in result

    ordered = sorted(latencies_ms)
    # nearest-rank p95
    idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
    p95 = ordered[idx]
    avg = statistics.mean(latencies_ms)

    print(f"H2 runs={len(latencies_ms)} avg={avg:.3f} ms p95={p95:.3f} ms (threshold 100 ms)")
    assert p95 <= 100.0, f"H2 FAIL: p95={p95:.3f} ms > 100 ms"
    print("H2 Traversal latency: PASS")
