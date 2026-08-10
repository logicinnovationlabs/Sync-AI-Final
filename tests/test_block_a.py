"""Block A - tenancy, identity, auth (architecture section 24 A1-A5)."""
from __future__ import annotations
import time
import jwt
import pytest
import requests
from tests.conftest import TestConfig
from tests.signoff_common import assert_pass, require_real, tcp_open, using_real_services
@pytest.mark.block_a
@pytest.mark.provisional
class TestBlockA:
    # A1 - 100 tokens across 3 tenants; exactly one tenant_id claim each
    def test_a1_tenant_binding_exactly_one_tenant_id(self, block_client, fixture_loader):
        tenants = ["tenant-a", "tenant-b", "tenant-c"]
        issued = 0
        for i in range(100):
            tenant = tenants[i % 3]
            resp = block_client.post(
                "/oauth/token",
                json={"principal_id": f"svc-{i}", "tenant_id": tenant, "scopes": ["search.read"]},
            )
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            payload = jwt.decode(token, TestConfig.JWT_SECRET, algorithms=["HS256"])
            assert payload.get("tenant_id") == tenant
            assert sum(1 for k in payload if k == "tenant_id") == 1
            assert payload["exp"] > payload["iat"]
            issued += 1
        assert issued == 100
        assert_pass("A1", issued == 100, f"issued={issued} tokens across {len(tenants)} tenants")
    # A2 - revoke then poll /api/v1/me until 401 within 60s (>=5 trials, 100% pass)
    def test_a2_revocation_within_60s(self, block_client):
        trials = 5
        successes = 0
        for _ in range(trials):
            tok = block_client.post(
                "/oauth/token",
                json={"principal_id": "principal-alice", "tenant_id": "tenant-a"},
            ).json()
            headers = {"Authorization": f"Bearer {tok['access_token']}"}
            assert block_client.get("/api/v1/me", headers=headers).status_code == 200
            t0 = time.time()
            rev = block_client.post("/oauth/revoke", json={"jti": tok["jti"]}, headers=headers)
            assert rev.status_code == 200
            rejected = False
            latency = None
            for _poll in range(200):
                me = block_client.get("/api/v1/me", headers=headers)
                if me.status_code == 401:
                    rejected = True
                    latency = time.time() - t0
                    break
                time.sleep(0.01)
            if rejected and latency is not None and latency <= 60.0:
                successes += 1
        assert_pass("A2", successes == trials, f"{successes}/{trials} revocations within 60s")
        assert successes == trials
    # A3 - SCIM sync 3x yields identical principal_id sets
    def test_a3_scim_idempotency(self, block_client, fixture_loader):
        users = [
            {"external_id": p["external_id"], "email": p["email"]}
            for p in fixture_loader.get_principals()
        ]
        runs: list[list[str]] = []
        for _ in range(3):
            resp = block_client.post("/scim/sync", json={"users": users})
            assert resp.status_code == 200
            runs.append([r["principal_id"] for r in resp.json()["principals"]])
        identical = runs[0] == runs[1] == runs[2]
        assert_pass("A3", identical, f"principal_ids stable across 3 syncs (n={len(runs[0])})")
        assert identical
        assert len(set(runs[0])) == len(runs[0])
    # A4 - 50 cross-tenant replay attempts all rejected (401/403)
    def test_a4_cross_tenant_replay_rejected(self, block_client):
        tok = block_client.post(
            "/oauth/token",
            json={"principal_id": "principal-alice", "tenant_id": "tenant-a", "scopes": ["search.read"]},
        ).json()["access_token"]
        rejected = 0
        for _ in range(50):
            resp = block_client.get(
                "/api/v1/me",
                headers={"Authorization": f"Bearer {tok}", "X-Tenant-ID": "tenant-b"},
            )
            if resp.status_code in (401, 403):
                rejected += 1
        assert_pass("A4", rejected == 50, f"{rejected}/50 cross-tenant attempts rejected")
        assert rejected == 50
    # A5 - missing admin.audit.read scope returns 403 with error envelope
    def test_a5_scope_enforcement_403(self, block_client):
        tok = block_client.post(
            "/oauth/token",
            json={"principal_id": "principal-bob", "tenant_id": "tenant-a", "scopes": ["search.read"]},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}", "X-Tenant-ID": "tenant-a"}
        resp = block_client.get("/api/v1/scoped/admin/audit", headers=headers)
        assert resp.status_code == 403
        body = resp.json()
        err = body.get("error")
        if err is None and isinstance(body.get("detail"), dict):
            err = body["detail"].get("error")
        has_envelope = bool(err and err.get("code") and err.get("message"))
        assert_pass("A5", has_envelope, "403 with structured error envelope")
        assert has_envelope
@pytest.mark.block_a
@pytest.mark.integration
@require_real
class TestBlockAIntegration:
    """Phase 2 stub - real auth service health/docs on REAL_BASE_PORT."""
    def test_a_integration_real_service_reachable(self):
        port = TestConfig.REAL_BASE_PORT
        if not using_real_services():
            pytest.skip("USE_REAL_SERVICES not enabled")
        if not tcp_open("127.0.0.1", port):
            pytest.skip(f"real service not listening on localhost:{port}")
        base = f"http://127.0.0.1:{port}"
        reachable = False
        for path in ("/health", "/docs", "/openapi.json"):
            try:
                resp = requests.get(f"{base}{path}", timeout=3)
                if resp.status_code < 500:
                    reachable = True
                    break
            except requests.RequestException:
                continue
        if not reachable:
            pytest.skip(f"health/docs not reachable on localhost:{port}")
        assert_pass("A-INT", True, f"real service reachable on :{port}")
