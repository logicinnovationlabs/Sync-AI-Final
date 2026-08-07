"""F3 — Index lag p95 < 30 seconds."""

from __future__ import annotations

import csv
import time
from pathlib import Path

import pytest

from app.consumers.canonical_consumer import CanonicalConsumer

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"


@pytest.mark.asyncio
async def test_F3_index_lag_p95(loaded_store, corpus):
    """
    F3 Signoff: publish 20 docs via ingest.canonical.v1 shape;
    measure time until searchable. p95 < 30s.
    """
    consumer = CanonicalConsumer(store=loaded_store)
    tenant_id = corpus["tenant_id"]
    lags_s = []
    rows = []

    for i in range(20):
        doc_id = f"doc-lag-{i:02d}"
        event = {
            "tenant_id": tenant_id,
            "payload": {
                "document_id": doc_id,
                "title": f"Index lag probe {i} uniqueToken{i} getUserInfo",
                "content": (
                    f"Canonical ingest lag sample {i}. "
                    f"Searchable marker uniqueToken{i} user_info."
                ),
                "object_type": "doc",
                "source": "fixture",
                "owner": "user:alice",
                "language": "en",
                "tags": ["lag"],
                "acl_filter_terms": ["group:eng", "user:alice"],
            },
        }
        t_publish = time.perf_counter()
        await consumer.process_event(event)

        found = False
        deadline = t_publish + 30.0
        while time.perf_counter() < deadline:
            result = await loaded_store.search(
                tenant_id=tenant_id,
                query=f"uniqueToken{i}",
                acl_terms=["group:eng", "user:alice"],
                size=10,
            )
            ids = {r["document_id"] for r in result["results"]}
            if doc_id in ids:
                found = True
                break
            time.sleep(0.01)

        lag = time.perf_counter() - t_publish
        lags_s.append(lag)
        rows.append({"sample": i, "document_id": doc_id, "lag_seconds": lag, "found": found})
        assert found, f"F3 FAIL: doc {doc_id} not searchable within 30s"

    ordered = sorted(lags_s)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    avg = sum(lags_s) / len(lags_s)
    print(f"\nF3 index lag: n={len(lags_s)} avg={avg:.4f}s p95={p95:.4f}s (threshold 30s)")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with (EVIDENCE / "lag_measurement.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["sample", "document_id", "lag_seconds", "found"])
        writer.writeheader()
        writer.writerows(rows)

    assert p95 < 30.0, f"F3 FAIL: p95={p95:.4f}s >= 30s"