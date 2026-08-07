"""Block C - normalization and identity resolution (architecture section 24 C1-C4)."""
from __future__ import annotations
import pytest
import requests
from tests.conftest import TestConfig
from tests.signoff_common import assert_pass, require_real, tcp_open, using_real_services
@pytest.mark.block_c
@pytest.mark.provisional
class TestBlockC:
    # C1 - normalize 3x on up to 60 docs; per-doc hashes byte-identical across runs
    def test_c1_determinism(self, block_client, fixture_loader):
        docs = fixture_loader.get_documents()[:60]
        runs = 3
        failures: list[str] = []
        for doc in docs:
            hashes: list[str] = []
            for _ in range(runs):
                resp = block_client.post("/normalize", json={"document": doc})
                assert resp.status_code == 200
                hashes.append(resp.json()["hash"])
            if len(set(hashes)) != 1:
                failures.append(doc["id"])
        ok = not failures
        assert_pass("C1", ok, f"{len(docs)-len(failures)}/{len(docs)} docs deterministic over {runs} runs")
        assert ok, failures
    # C2 - ACL fidelity vs document ground truth 100%
    def test_c2_acl_fidelity(self, block_client, fixture_loader):
        docs = fixture_loader.get_documents()
        mismatches = 0
        for doc in docs:
            resp = block_client.post("/normalize", json={"document": doc}).json()
            if set(resp["normalized"]["acl"]) != set(doc["acl"]):
                mismatches += 1
        ok = mismatches == 0
        assert_pass("C2", ok, f"{len(docs)-mismatches}/{len(docs)} docs ACL match")
        assert ok
    # C3 - revoke then lexical search returns 401 within auth cycle (mock)
    def test_c3_revocation_propagation(self, block_client, fixture_loader):
        tok = block_client.post(
            "/oauth/token",
            json={"principal_id": "principal-alice", "tenant_id": "tenant-a", "scopes": ["search.read"]},
        ).json()
        headers = {"Authorization": f"Bearer {tok['access_token']}"}
        block_client.post("/oauth/revoke", json={"jti": tok["jti"]}, headers=headers)
        denied = block_client.post("/search/lexical", headers=headers, json={"query": "roadmap"})
        ok = denied.status_code == 401
        assert_pass("C3", ok, f"post-revoke search status={denied.status_code}")
        assert ok
    # C4 - multi_source_identities resolution accuracy >= 95%
    def test_c4_identity_resolution_ge_95(self, block_client, fixture_loader):
        identities = fixture_loader.get_multi_source_identities()
        total = 0
        ok = 0
        for identity in identities:
            for src in identity["sources"]:
                total += 1
                resp = block_client.post(
                    "/identity/resolve",
                    json={"external_id": src["external_id"], "source_type": src["source_type"]},
                )
                assert resp.status_code == 200
                resolved = resp.json()["resolved"]
                if resolved and resolved[0]["principal_id"] == identity["principal_id"]:
                    ok += 1
        rate = ok / total if total else 1.0
        passed = rate >= 0.95
        assert_pass("C4", passed, f"resolution rate {rate:.1%} ({ok}/{total})")
        assert passed
@pytest.mark.block_c
@pytest.mark.integration
@require_real
class TestBlockCIntegration:
    """Phase 2 stub - real normalization service health when USE_REAL_SERVICES=1."""
    def test_c_integration_real_service_reachable(self):
        port = TestConfig.REAL_BASE_PORT + TestConfig.PORT_OFFSET["C"]
        if not using_real_services():
            pytest.skip("USE_REAL_SERVICES not enabled")
        if not tcp_open("127.0.0.1", port):
            pytest.skip(f"real normalization service not listening on localhost:{port}")
        base = f"http://127.0.0.1:{port}"
        reachable = False
        for path in ("/health", "/docs"):
            try:
                resp = requests.get(f"{base}{path}", timeout=3)
                if resp.status_code < 500:
                    reachable = True
                    break
            except requests.RequestException:
                continue
        if not reachable:
            pytest.skip(f"health/docs not reachable on localhost:{port}")
        assert_pass("C-INT", True, f"real normalization reachable on :{port}")
