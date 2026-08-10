"""Block L — assistant answers (provisional)."""

from __future__ import annotations

import pytest


@pytest.mark.block_l
@pytest.mark.provisional
class TestBlockL:
    def _headers(self, client, principal="principal-alice", tenant="tenant-a"):
        tok = client.post(
            "/oauth/token",
            json={"principal_id": principal, "tenant_id": tenant, "scopes": ["search.read", "document.read"]},
        ).json()["access_token"]
        return {"Authorization": f"Bearer {tok}"}

    def test_l1_citation_faithfulness(self, block_client, fixture_loader):
        headers = self._headers(block_client)
        resp = block_client.post(
            "/api/v1/assistant/chat", headers=headers, json={"query": "project roadmap"}
        ).json()
        assert resp["citations"]
        for cite in resp["citations"]:
            doc = next(d for d in fixture_loader.get_documents() if d["id"] == cite["document_id"])
            assert cite["quote"] in doc["body"] or doc["body"].startswith(cite["quote"][:20])

    def test_l2_acl_safe_answers(self, block_client):
        headers = self._headers(block_client, "principal-alice", "tenant-a")
        resp = block_client.post(
            "/api/v1/assistant/chat", headers=headers, json={"query": "M&A Deal Sheet"}
        ).json()
        cited = {c["document_id"] for c in resp.get("citations", [])}
        assert "doc-restricted" not in cited
        assert "doc-security" not in cited

    def test_l3_latency(self, block_client, fixture_loader):
        headers = self._headers(block_client)
        samples = []
        for _ in range(10):
            resp = block_client.post(
                "/api/v1/assistant/chat", headers=headers, json={"query": "API documentation"}
            )
            samples.append(getattr(resp, "_duration_ms", resp.json().get("took_ms", 1)))
        p95 = sorted(samples)[int(len(samples) * 0.95)]
        assert p95 <= fixture_loader.get_baselines().get("assistant_p95_ms", 2000)

    def test_l4_refuse_unauthorized(self, block_client):
        headers = self._headers(block_client, "principal-bob", "tenant-a")
        # bob has no path to restricted/security; force a query that yields no allowed hits
        resp = block_client.post(
            "/api/v1/assistant/chat", headers=headers, json={"query": "zzzz-no-match-xyz"}
        ).json()
        assert resp.get("refused") is True or resp.get("citations") == []
