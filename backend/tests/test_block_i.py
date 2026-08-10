"""Block I — user signals (provisional / mock-only)."""

from __future__ import annotations

import pytest


@pytest.mark.block_i
@pytest.mark.provisional
class TestBlockI:
    def _headers(self, client, principal, tenant):
        tok = client.post(
            "/oauth/token",
            json={"principal_id": principal, "tenant_id": tenant, "scopes": ["search.read"]},
        ).json()["access_token"]
        return {"Authorization": f"Bearer {tok}"}

    def test_i1_signal_freshness(self, block_client):
        headers = self._headers(block_client, "principal-alice", "tenant-a")
        resp = block_client.get("/signals/user/principal-alice", headers=headers).json()
        assert resp["signals"]
        assert all(s.get("freshness_s", 9999) <= 3600 for s in resp["signals"])

    def test_i2_ranking_contribution(self, block_client):
        headers = self._headers(block_client, "principal-alice", "tenant-a")
        resp = block_client.get("/signals/user/principal-alice", headers=headers).json()
        assert resp.get("ranking_boost", 0) > 0

    def test_i3_tenant_isolation(self, block_client):
        headers = self._headers(block_client, "principal-alice", "tenant-a")
        resp = block_client.get("/signals/user/principal-carol", headers=headers)
        assert resp.status_code == 403
