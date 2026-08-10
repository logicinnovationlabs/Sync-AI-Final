"""Block N — admin / audit / config (provisional)."""

from __future__ import annotations

import pytest


@pytest.mark.block_n
@pytest.mark.provisional
class TestBlockN:
    def test_n1_audit_completeness(self, block_client):
        # generate events
        block_client.post("/scim/sync", json={"users": []})
        block_client.post("/tenants/tenant-a/provision")
        tok = block_client.post(
            "/oauth/token",
            json={
                "principal_id": "principal-carol",
                "tenant_id": "tenant-b",
                "scopes": ["admin.audit.read", "search.read"],
            },
        ).json()["access_token"]
        events = block_client.get(
            "/admin/audit", headers={"Authorization": f"Bearer {tok}"}
        ).json()["events"]
        types = {e["type"] for e in events}
        assert "scim_sync" in types or "provision" in types
        assert all("timestamp" in e and "id" in e for e in events)

    def test_n2_rbac(self, block_client):
        tok = block_client.post(
            "/oauth/token",
            json={"principal_id": "principal-bob", "tenant_id": "tenant-a", "scopes": ["search.read"]},
        ).json()["access_token"]
        resp = block_client.get("/admin/audit", headers={"Authorization": f"Bearer {tok}"})
        assert resp.status_code == 403

    def test_n3_config_safety(self, block_client):
        tok = block_client.post(
            "/oauth/token",
            json={
                "principal_id": "principal-carol",
                "tenant_id": "tenant-b",
                "scopes": ["admin.audit.read"],
            },
        ).json()["access_token"]
        cfg = block_client.get("/admin/config", headers={"Authorization": f"Bearer {tok}"}).json()
        assert cfg.get("secrets_present") is False
        blob = str(cfg).lower()
        for needle in ["password", "private_key", "jwt_test_secret", "sk-"]:
            assert needle not in blob
