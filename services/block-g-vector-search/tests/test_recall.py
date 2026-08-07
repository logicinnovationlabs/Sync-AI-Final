"""G1 — Recall@10 >= 0.85 against relevance_labels.json."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_G1_recall_at_10(loaded_store, relevance, corpus):
    """
    G1 Signoff: average Recall@10 across 30 labeled queries must be >= 0.85.
    """
    queries = relevance["queries"]
    assert len(queries) == 30, "Block Z relevance set must contain 30 queries"

    recalls = []
    for q in queries:
        results = await loaded_store.search(
            tenant_id=q["tenant_id"],
            query_embedding=q["query_embedding"],
            acl_terms=q["acl_filter_terms"],
            top_k=10,
            model_version=q.get("model_version"),
        )
        returned = {r["chunk_id"] for r in results}
        relevant = set(q["relevant_chunk_ids"])
        hit = len(returned & relevant)
        recall = hit / len(relevant) if relevant else 0.0
        recalls.append(recall)
        print(
            f"  {q['query_id']}: recall={recall:.2f} "
            f"hits={sorted(returned & relevant)} top={[r['chunk_id'] for r in results[:3]]}"
        )

    avg = sum(recalls) / len(recalls)
    print(f"\nG1 Recall@10 average: {avg:.4f} (threshold 0.85)")
    assert avg >= 0.85, f"G1 FAIL: Recall@10={avg:.4f} < 0.85"