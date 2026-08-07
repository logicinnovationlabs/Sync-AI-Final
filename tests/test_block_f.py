"""Block F — lexical search (Phase 1 mocks)."""

from __future__ import annotations

import pytest

from tests.conftest import perf_tracker
from tests.helpers.performance import detect_regression
from tests.signoff_common import assert_pass, p95


@pytest.mark.block_f
@pytest.mark.provisional
class TestBlockF:
    def _token(self, client, principal="principal-alice", tenant="tenant-a"):
        return client.post(
            "/oauth/token",
            json={"principal_id": principal, "tenant_id": tenant, "scopes": ["search.read"]},
        ).json()["access_token"]

    def _query_list(self, fixture_loader, count: int = 100):
        labels = fixture_loader.get_relevance_labels()
        base = [item["query"] for item in labels if item.get("query")]
        base.extend(["roadmap", "API", "eng", "Deal", "Security Policy", "project"])
        if not base:
            base = ["roadmap"]
        return [base[i % len(base)] for i in range(count)]

    def test_f1_latency_p95_le_200ms(self, block_client, fixture_loader):
        """F1: up to 100 lexical queries; p95 at most 200ms."""
        tok = self._token(block_client)
        headers = {"Authorization": f"Bearer {tok}"}
        queries = self._query_list(fixture_loader, 100)
        samples = []
        for query in queries:
            resp = block_client.post(
                "/search/lexical",
                headers=headers,
                json={"query": query},
            )
            assert resp.status_code == 200
            samples.append(getattr(resp, "_duration_ms", resp.json().get("took_ms", 1)))
        for sample in samples:
            perf_tracker.record("lexical", sample)
        p95_ms = p95(samples)
        baseline = fixture_loader.get_baselines().get("lexical_p95_ms", 200)
        ok = p95_ms <= baseline and not detect_regression(p95_ms, baseline)
        assert_pass("F1", ok, f"p95={p95_ms:.1f}ms n={len(samples)} threshold={baseline}ms")

    def test_f2_acl_zero_leaks(self, block_client):
        """F2: ACL red-team — forbidden docs never appear in hits."""
        tok = self._token(block_client, "principal-alice", "tenant-a")
        headers = {"Authorization": f"Bearer {tok}"}
        hits = block_client.post(
            "/search/lexical",
            headers=headers,
            json={"query": "Deal"},
        ).json()["hits"]
        hit_ids = {h["document_id"] for h in hits}
        forbidden = {"doc-restricted", "doc-security"}
        assert_pass("F2", hit_ids.isdisjoint(forbidden), f"hits={sorted(hit_ids)}")

    def test_f3_index_lag(self, block_client):
        """F3: index lag within threshold."""
        tok = self._token(block_client)
        resp = block_client.post(
            "/search/lexical",
            headers={"Authorization": f"Bearer {tok}"},
            json={"query": "API"},
        ).json()
        lag_ms = resp.get("index_lag_ms", 0)
        assert_pass("F3", lag_ms <= 1000, f"index_lag_ms={lag_ms}")

    def test_f4_facet_accuracy(self, block_client, fixture_loader):
        """F4: facet counts match ACL-visible fixture documents."""
        tok = self._token(block_client)
        resp = block_client.post(
            "/search/lexical",
            headers={"Authorization": f"Bearer {tok}"},
            json={"query": "eng"},
        ).json()
        allowed = fixture_loader.docs_for_principal("principal-alice")
        expected = {}
        for doc in allowed:
            expected[doc["source"]] = expected.get(doc["source"], 0) + 1
        match = resp["facets"] == expected
        assert_pass("F4", match, f"expected={expected} actual={resp['facets']}")
