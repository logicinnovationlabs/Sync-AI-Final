"""G3 — Query latency p95 <= 150 ms."""

from __future__ import annotations

import time

import pytest


@pytest.mark.asyncio
async def test_G3_latency_p95(loaded_store, relevance, corpus):
    """
    G3 Signoff: 100 representative searches, p95 end-to-end <= 150ms.
    """
    queries = relevance["queries"]
    latencies_ms = []

    # Mix of query embeddings, top-k values
    for i in range(100):
        q = queries[i % len(queries)]
        top_k = [10, 25, 50, 100][i % 4]
        t0 = time.perf_counter()
        await loaded_store.search(
            tenant_id=q["tenant_id"],
            query_embedding=q["query_embedding"],
            acl_terms=q["acl_filter_terms"],
            top_k=top_k,
            model_version=q.get("model_version"),
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    ordered = sorted(latencies_ms)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    avg = sum(latencies_ms) / len(latencies_ms)
    print(f"\nG3 latency: n={len(latencies_ms)} avg={avg:.2f}ms p95={p95:.2f}ms (threshold 150ms)")
    assert p95 <= 150.0, f"G3 FAIL: p95={p95:.2f}ms > 150ms"