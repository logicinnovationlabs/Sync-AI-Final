"""F1 — Query latency p95 <= 200 ms."""

from __future__ import annotations

import time

import pytest


@pytest.mark.asyncio
async def test_F1_query_latency_p95(loaded_store, queries):
    """
    F1 Signoff: 100 representative queries against 60-doc fixture, p95 <= 200ms.
    """
    qlist = queries["queries"]
    assert len(qlist) >= 100
    latencies_ms = []

    for i in range(100):
        q = qlist[i]
        t0 = time.perf_counter()
        await loaded_store.search(
            tenant_id=q["tenant_id"],
            query=q["query"],
            acl_terms=q["acl_filter_terms"],
            size=[10, 20, 50, 100][i % 4],
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    ordered = sorted(latencies_ms)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    avg = sum(latencies_ms) / len(latencies_ms)
    print(
        f"\nF1 latency: n={len(latencies_ms)} avg={avg:.2f}ms "
        f"p95={p95:.2f}ms (threshold 200ms)"
    )
    assert p95 <= 200.0, f"F1 FAIL: p95={p95:.2f}ms > 200ms"