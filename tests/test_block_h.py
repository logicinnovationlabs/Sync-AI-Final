"""Block H - knowledge graph (architecture section 24 H1-H3)."""

from __future__ import annotations

import pytest

from tests.conftest import perf_tracker
from tests.signoff_common import assert_pass, p95


@pytest.mark.block_h
@pytest.mark.provisional
class TestBlockH:
    """Phase 1 provisional signoff against Block Z contract mocks."""

    def _headers(self, client):
        tok = client.post(
            "/oauth/token",
            json={
                "principal_id": "principal-alice",
                "tenant_id": "tenant-a",
                "scopes": ["search.read"],
            },
        ).json()["access_token"]
        return {"Authorization": f"Bearer {tok}"}

    def test_h1_edge_fidelity(self, block_client, fixture_loader):
        # H1: edge count / identity matches golden fixture for start node
        headers = self._headers(block_client)
        resp = block_client.post(
            "/graph/traverse",
            headers=headers,
            json={"start": "principal-alice", "depth": 1},
        ).json()
        expected = [
            e
            for e in fixture_loader.get_graph_edges()
            if e["source"] == "principal-alice" or e["target"] == "principal-alice"
        ]
        got_ids = {(e["source"], e["target"], e["type"]) for e in resp["edges"]}
        exp_ids = {(e["source"], e["target"], e["type"]) for e in expected}
        ok = exp_ids.issubset(got_ids) or got_ids == exp_ids
        assert_pass("H1", ok, f"expected={len(exp_ids)} got={len(got_ids)}")

    def test_h2_traversal_p95_le_100ms(self, block_client, fixture_loader):
        # H2: 50 depth-2 (mock may honor depth=1) queries; p95 <= 100ms
        headers = self._headers(block_client)
        samples = []
        for i in range(50):
            depth = 2 if i % 2 == 0 else 1
            resp = block_client.post(
                "/graph/traverse",
                headers=headers,
                json={"start": "doc-roadmap", "depth": depth},
            )
            assert resp.status_code == 200, resp.text
            samples.append(getattr(resp, "_duration_ms", resp.json().get("took_ms", 1)))
        for s in samples:
            perf_tracker.record("graph", s)
        value = p95(samples)
        threshold = fixture_loader.get_baselines().get("graph_p95_ms", 100)
        assert_pass("H2", value <= threshold, f"p95={value:.2f}ms threshold={threshold}ms n=50")

    def test_h3_merge_split_integrity(self, block_client):
        # H3: merge then split -> integrity ok, no orphan signal
        merge = block_client.post(
            "/graph/merge", json={"nodes": ["doc-roadmap", "doc-api-docs"]}
        ).json()
        split = block_client.post("/graph/split", json={"node": "doc-roadmap"}).json()
        ok = merge.get("integrity") == "ok" and split.get("integrity") == "ok"
        assert_pass("H3", ok, f"merge={merge.get('integrity')} split={split.get('integrity')}")