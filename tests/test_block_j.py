"""Block J - query federator (architecture section 24 J1-J4)."""

from __future__ import annotations

import math

import pytest

from tests.conftest import perf_tracker
from tests.signoff_common import assert_pass, p95


def _dcg(rels):
    return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))


@pytest.mark.block_j
@pytest.mark.provisional
class TestBlockJ:
    """Phase 1 provisional signoff against Block Z contract mocks."""

    def _headers(self, client, principal="principal-alice", tenant="tenant-a"):
        tok = client.post(
            "/oauth/token",
            json={
                "principal_id": principal,
                "tenant_id": tenant,
                "scopes": ["search.read"],
            },
        ).json()["access_token"]
        return {"Authorization": f"Bearer {tok}"}

    def test_j1_p95_le_800ms(self, block_client, fixture_loader):
        # J1: 100 federated queries; p95 <= 800ms
        headers = self._headers(block_client)
        samples = []
        for i in range(100):
            resp = block_client.post(
                "/api/v1/search",
                headers=headers,
                json={"query": "roadmap" if i % 2 == 0 else "API"},
            )
            assert resp.status_code == 200, resp.text
            samples.append(getattr(resp, "_duration_ms", resp.json().get("took_ms", 1)))
        for s in samples:
            perf_tracker.record("federator", s)
        value = p95(samples)
        threshold = fixture_loader.get_baselines().get("federator_p95_ms", 800)
        assert_pass("J1", value <= threshold, f"p95={value:.2f}ms threshold={threshold}ms n=100")

    def test_j2_redteam_zero_unauthorized(self, block_client, fixture_loader):
        # J2: 15 red-team cases -> 0 unauthorized document ids
        unauthorized = 0
        cases = fixture_loader.get_red_team_cases()
        for case in cases:
            headers = self._headers(block_client, case["principal_id"], case["tenant_id"])
            hits = block_client.post(
                "/api/v1/search",
                headers=headers,
                json={"query": case["query"]},
            ).json()["hits"]
            hit_ids = {h["document_id"] for h in hits}
            leaked = hit_ids.intersection(set(case.get("forbidden_document_ids") or []))
            unauthorized += len(leaked)
        assert_pass(
            "J2",
            unauthorized == 0,
            f"cases={len(cases)} unauthorized={unauthorized}",
        )

    def test_j3_ndcg_at_10_ge_080(self, block_client, fixture_loader):
        # J3: NDCG@10 >= 0.80 on labeled relevance set
        headers = self._headers(block_client)
        labels = [l for l in fixture_loader.get_relevance_labels() if l["tenant_id"] == "tenant-a"]
        by_query = {}
        for lab in labels:
            by_query.setdefault(lab["query"], []).append(lab)
        scores = []
        for query, labs in by_query.items():
            rel_map = {l["document_id"]: l["relevance"] for l in labs}
            hits = block_client.post(
                "/api/v1/search", headers=headers, json={"query": query}
            ).json()["hits"][:10]
            actual = [rel_map.get(h["document_id"], 0) for h in hits]
            ideal = sorted(rel_map.values(), reverse=True)[:10]
            idcg = _dcg(ideal) or 1.0
            scores.append(_dcg(actual) / idcg)
        ndcg = sum(scores) / len(scores) if scores else 0.0
        assert_pass("J3", ndcg >= 0.80, f"NDCG@10={ndcg:.4f} queries={len(scores)}")

    def test_j4_graceful_degradation(self, block_client):
        # J4: degrade backends -> partial OK, no 5xx
        headers = self._headers(block_client)
        resp = block_client.post(
            "/api/v1/search",
            headers=headers,
            json={"query": "roadmap", "force_degrade": True},
        )
        assert resp.status_code < 500, resp.text
        body = resp.json()
        ok = body.get("degraded") is True and isinstance(body.get("hits"), list)
        assert_pass(
            "J4",
            ok,
            f"degraded={body.get('degraded')} sources={body.get('sources')} status={resp.status_code}",
        )