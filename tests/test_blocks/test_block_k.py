"""Block K — document reader (provisional)."""

from __future__ import annotations

import pytest

from tests.conftest import perf_tracker


@pytest.mark.block_k
@pytest.mark.provisional
class TestBlockK:
    def _headers(self, client, principal="principal-alice", tenant="tenant-a"):
        tok = client.post(
            "/oauth/token",
            json={"principal_id": principal, "tenant_id": tenant, "scopes": ["document.read", "search.read"]},
        ).json()["access_token"]
        return {"Authorization": f"Bearer {tok}"}

    def test_k1_read_completeness(self, block_client, fixture_loader):
        headers = self._headers(block_client)
        doc = next(d for d in fixture_loader.get_documents() if d["id"] == "doc-roadmap")
        resp = block_client.post("/api/v1/read", headers=headers, json={"document_id": doc["id"]}).json()
        assert resp["complete"] is True
        assert resp["body"] == doc["body"]
        assert resp["title"] == doc["title"]

    def test_k2_acl_on_read(self, block_client):
        headers = self._headers(block_client, "principal-alice", "tenant-a")
        resp = block_client.post("/api/v1/read", headers=headers, json={"document_id": "doc-restricted"})
        assert resp.status_code == 403

    def test_k3_latency(self, block_client, fixture_loader):
        headers = self._headers(block_client)
        samples = []
        for _ in range(10):
            resp = block_client.post("/api/v1/read", headers=headers, json={"document_id": "doc-roadmap"})
            samples.append(getattr(resp, "_duration_ms", resp.json().get("took_ms", 1)))
        for s in samples:
            perf_tracker.record("reader", s)
        p95 = sorted(samples)[int(len(samples) * 0.95)]
        assert p95 <= fixture_loader.get_baselines().get("reader_p95_ms", 300)
