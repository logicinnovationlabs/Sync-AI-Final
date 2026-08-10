"""Block E — chunking and embeddings (Phase 1 mocks)."""

from __future__ import annotations

import time

import pytest

from tests.signoff_common import assert_pass


@pytest.mark.block_e
@pytest.mark.provisional
class TestBlockE:
    def test_e1_chunk_integrity(self, block_client, fixture_loader):
        """E1: /embed chunk ids match /chunks listing."""
        doc = fixture_loader.get_documents()[0]
        emb = block_client.post("/embed", json={"document_id": doc["id"]}).json()
        chunks = block_client.get(f"/chunks/{doc['id']}").json()["chunks"]
        ids_match = [c["id"] for c in emb["chunks"]] == chunks
        dims_ok = all(len(c["vector"]) == c["embedding_dim"] for c in emb["chunks"])
        assert_pass("E1", ids_match and dims_ok, f"doc={doc['id']} chunks={len(chunks)}")

    def test_e2_throughput_gate_structural(self, block_client, fixture_loader):
        """E2: embed all fixture docs; estimate docs/min from wall time."""
        docs = fixture_loader.get_documents()
        t0 = time.perf_counter()
        for doc in docs:
            resp = block_client.post("/embed", json={"document_id": doc["id"]})
            assert resp.status_code == 200
            assert len(resp.json()["chunks"]) >= 1
        elapsed_s = time.perf_counter() - t0
        docs_per_min = (len(docs) / elapsed_s) * 60.0 if elapsed_s > 0 else 0.0
        detail = f"docs/min~={docs_per_min:.1f} over {len(docs)} docs in {elapsed_s:.2f}s"
        if elapsed_s < 60:
            detail += "; Phase-2 target 500/min deferred (short mock wall time)"
        assert_pass("E2", docs_per_min > 0, detail)

    def test_e3_reembed_trigger(self, block_client):
        """E3: /reembed returns triggered=true."""
        resp = block_client.post(
            "/reembed",
            json={"document_id": "doc-roadmap", "reason": "model_bump"},
        )
        assert resp.status_code == 200
        triggered = resp.json().get("triggered") is True
        assert_pass("E3", triggered, "reembed triggered")

    def test_e4_idempotency(self, block_client):
        """E4: identical chunk ids across repeated embed calls."""
        payload = {"document_id": "doc-api-docs"}
        a = block_client.post("/embed", json=payload).json()
        b = block_client.post("/embed", json=payload).json()
        ids_a = [c["id"] for c in a["chunks"]]
        ids_b = [c["id"] for c in b["chunks"]]
        assert_pass("E4", ids_a == ids_b, f"chunk_ids={ids_a}")
