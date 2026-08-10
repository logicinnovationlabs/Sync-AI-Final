"""Block G — vector search (Phase 1 mocks)."""

from __future__ import annotations

import pytest

from tests.conftest import perf_tracker
from tests.signoff_common import assert_pass, p95


@pytest.mark.block_g
@pytest.mark.provisional
class TestBlockG:
    def _headers(self, client, principal="principal-alice", tenant="tenant-a"):
        tok = client.post(
            "/oauth/token",
            json={"principal_id": principal, "tenant_id": tenant, "scopes": ["search.read"]},
        ).json()["access_token"]
        return {"Authorization": f"Bearer {tok}"}

    def test_g1_recall_at_10_ge_085(self, block_client, fixture_loader):
        """G1: recall@10 at least 0.85 on labeled queries."""
        headers = self._headers(block_client)
        labels = [l for l in fixture_loader.get_relevance_labels() if l["tenant_id"] == "tenant-a"]
        hits_at_10 = 0
        for label in labels:
            resp = block_client.post(
                "/search/vector",
                headers=headers,
                json={"query": label["query"]},
            ).json()
            ids = [h["document_id"] for h in resp["hits"][:10]]
            if label["document_id"] in ids:
                hits_at_10 += 1
        recall = hits_at_10 / len(labels) if labels else 0.0
        assert_pass("G1", recall >= 0.85, f"recall@10={recall:.3f}")

    def test_g2_acl_zero_leaks(self, block_client):
        """G2: restricted documents never returned for principal-bob."""
        headers = self._headers(block_client, "principal-bob", "tenant-a")
        hits = block_client.post(
            "/search/vector",
            headers=headers,
            json={"query": "Security Policy"},
        ).json()["hits"]
        leaked = any(h["document_id"] == "doc-security" for h in hits)
        assert_pass("G2", not leaked, f"hits={len(hits)}")

    def test_g3_p95_le_150ms(self, block_client, fixture_loader):
        """G3: vector search p95 at most 150ms."""
        headers = self._headers(block_client)
        samples = []
        for _ in range(20):
            resp = block_client.post(
                "/search/vector",
                headers=headers,
                json={"query": "roadmap"},
            )
            samples.append(getattr(resp, "_duration_ms", resp.json().get("took_ms", 1)))
        for sample in samples:
            perf_tracker.record("vector", sample)
        p95_ms = p95(samples)
        baseline = fixture_loader.get_baselines().get("vector_p95_ms", 150)
        assert_pass("G3", p95_ms <= baseline, f"p95={p95_ms:.1f}ms threshold={baseline}ms")

    def test_g4_model_version_handling(self, block_client):
        """G4: model_version request tag echoed in response."""
        headers = self._headers(block_client)
        model_version = "v2-test"
        resp = block_client.post(
            "/search/vector",
            headers=headers,
            json={"query": "API", "model_version": model_version},
        ).json()
        tagged = resp.get("model_version") == model_version
        assert_pass("G4", tagged, f"model_version={resp.get('model_version')}")
