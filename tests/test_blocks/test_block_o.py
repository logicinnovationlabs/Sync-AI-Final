"""Block O — observability (provisional)."""

from __future__ import annotations

import pytest


@pytest.mark.block_o
@pytest.mark.provisional
class TestBlockO:
    def test_o1_trace_propagation(self, block_client):
        traces = block_client.get("/traces").json()["traces"]
        assert traces
        for tr in traces:
            tid = tr["trace_id"]
            assert all(span.get("trace_id") == tid for span in tr["spans"])

    def test_o2_metric_cardinality(self, block_client):
        metrics = block_client.get("/metrics").json()
        assert metrics.get("cardinality_ok") is True
        # no high-cardinality principal_id labels
        for m in metrics["metrics"]:
            labels = m.get("labels") or {}
            assert "principal_id" not in labels
            assert "email" not in labels

    def test_o3_log_redaction(self, block_client, fixture_loader):
        # Ensure crawl/search responses do not echo forbidden credential patterns.
        patterns = fixture_loader.load("crawl_expectations").get("credentials_forbidden_patterns", [])
        tok = block_client.post(
            "/oauth/token",
            json={
                "principal_id": "principal-carol",
                "tenant_id": "tenant-b",
                "scopes": ["admin.audit.read"],
            },
        ).json()["access_token"]
        surfaces = [
            block_client.get("/metrics").text,
            block_client.get("/health").text,
            block_client.get("/admin/config", headers={"Authorization": f"Bearer {tok}"}).text,
        ]
        for text in surfaces:
            for pat in patterns:
                assert pat not in text

    def test_o4_health_alert_surface(self, block_client):
        health = block_client.get("/health").json()
        assert health.get("status") == "ok"
        metrics = block_client.get("/metrics").json()
        assert "metrics" in metrics
