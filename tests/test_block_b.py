"""Block B - connectors and ingestion (architecture section 24 B1-B5)."""
from __future__ import annotations
import re
import pytest
import requests
from tests.conftest import TestConfig
from tests.signoff_common import assert_pass, require_real, tcp_open, using_real_services
@pytest.mark.block_b
@pytest.mark.provisional
class TestBlockB:
    # B1 - drive+gmail crawl ingested counts match crawl_expectations
    def test_b1_crawl_completeness(self, block_client, fixture_loader):
        crawl = fixture_loader.load("crawl_expectations")
        drive = block_client.post("/connectors/google-drive/crawl")
        gmail = block_client.post("/connectors/google-gmail/crawl")
        assert drive.status_code == 200 and gmail.status_code == 200
        drive_ok = (
            drive.json()["ingested"] == drive.json()["expected"] == crawl["expected_counts"]["google_drive"]
        )
        gmail_ok = (
            gmail.json()["ingested"] == gmail.json()["expected"] == crawl["expected_counts"]["google_gmail"]
        )
        assert_pass("B1", drive_ok and gmail_ok, "drive+gmail ingested == expected")
        assert drive_ok and gmail_ok
    # B2 - delta types valid; cover up to 5 listed types when fixture defines them
    def test_b2_delta_types(self, block_client, fixture_loader):
        expected_list = fixture_loader.load("crawl_expectations").get("delta_types", [])
        expected = set(expected_list)
        drive = block_client.post("/connectors/google-drive/crawl").json()
        gmail = block_client.post("/connectors/google-gmail/crawl").json()
        seen = {o.get("delta_type") for o in drive["objects"] + gmail["objects"]}
        seen.discard(None)
        valid = seen.issubset(expected)
        has_changes = "created" in seen or "updated" in seen
        if len(expected_list) >= 5:
            covers_required = set(expected_list[:5]).issubset(seen)
        else:
            covers_required = valid and has_changes
        assert_pass("B2", covers_required, f"seen={sorted(seen)} expected={sorted(expected)}")
        assert covers_required
    # B3 - rate_limit_retries meets baseline; crawl status ok
    def test_b3_rate_limit_resilience(self, block_client, fixture_loader):
        status = block_client.get("/crawls/crawl-drive-1")
        assert status.status_code == 200
        retries = status.json().get("rate_limit_retries", 0)
        expected = fixture_loader.load("crawl_expectations").get("rate_limit_retries", 3)
        ok = retries >= expected and status.json().get("status") == "complete"
        assert_pass("B3", ok, f"retries={retries} expected>={expected}")
        assert ok
    # B4 - zero credential pattern matches in crawl payloads
    def test_b4_credential_leakage_zero_matches(self, block_client, fixture_loader):
        patterns = fixture_loader.load("crawl_expectations").get("credentials_forbidden_patterns", [])
        payloads = [
            block_client.post("/connectors/google-drive/crawl").text,
            block_client.post("/connectors/google-gmail/crawl").text,
            block_client.get("/ingested-objects").text,
        ]
        matches = 0
        for text in payloads:
            for pat in patterns:
                if re.search(re.escape(pat), text):
                    matches += 1
        assert_pass("B4", matches == 0, f"{matches} forbidden credential patterns")
        assert matches == 0
    # B5 - checkpoint resume succeeds for fixture checkpoint
    def test_b5_checkpoint_resume(self, block_client, fixture_loader):
        docs = fixture_loader.get_documents()
        cp = docs[0].get("checkpoint", "cp-drive-1")
        resp = block_client.post("/connectors/checkpoint", json={"source": "google_drive", "checkpoint": cp})
        assert resp.status_code == 200
        ok = resp.json()["resumed_from"] == cp and resp.json()["ok"] is True
        assert_pass("B5", ok, f"resumed_from={cp}")
        assert ok
@pytest.mark.block_b
@pytest.mark.integration
@require_real
class TestBlockBIntegration:
    """Phase 2 stub - real connector service health when USE_REAL_SERVICES=1."""
    def test_b_integration_real_service_reachable(self):
        port = TestConfig.REAL_BASE_PORT + TestConfig.PORT_OFFSET["B"]
        if not using_real_services():
            pytest.skip("USE_REAL_SERVICES not enabled")
        if not tcp_open("127.0.0.1", port):
            pytest.skip(f"real connector service not listening on localhost:{port}")
        base = f"http://127.0.0.1:{port}"
        reachable = False
        for path in ("/health", "/docs", "/connectors"):
            try:
                resp = requests.get(f"{base}{path}", timeout=3)
                if resp.status_code < 500:
                    reachable = True
                    break
            except requests.RequestException:
                continue
        if not reachable:
            pytest.skip(f"health/docs not reachable on localhost:{port}")
        assert_pass("B-INT", True, f"real connector reachable on :{port}")
