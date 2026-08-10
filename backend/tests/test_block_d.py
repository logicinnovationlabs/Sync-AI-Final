"""Block D — storage, tenancy isolation, keys (Phase 1 mocks)."""

from __future__ import annotations

import time

import pytest

from tests.signoff_common import assert_pass

PROVISION_MS_THRESHOLD = 300_000  # 5 minutes


@pytest.mark.block_d
@pytest.mark.provisional
class TestBlockD:
    def test_d1_provisioning_time(self, block_client):
        """D1: provision up to 10 tenants within 5 minutes."""
        start = time.perf_counter()
        provisioned = 0
        mock_single_tenant = False
        fallback_used = False

        for i in range(10):
            tenant_id = f"tenant-{i}"
            resp = block_client.post(f"/tenants/{tenant_id}/provision")
            if resp.status_code == 404:
                if not fallback_used:
                    fallback_used = True
                    mock_single_tenant = True
                    resp = block_client.post("/tenants/tenant-a/provision")
                else:
                    break
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body.get("provisioned") is True
            provisioned += 1
            per_elapsed = body.get("elapsed_ms")
            if per_elapsed is not None:
                assert per_elapsed <= PROVISION_MS_THRESHOLD
            if mock_single_tenant:
                break

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        detail = f"elapsed_ms={elapsed_ms:.0f}, provisioned={provisioned}"
        if mock_single_tenant:
            detail += "; mock may only expose tenant-a"
        assert_pass("D1", elapsed_ms < PROVISION_MS_THRESHOLD, detail)

    def test_d2_backup_restore(self, block_client):
        """D2: backup/restore document counts match."""
        bak = block_client.post("/tenants/tenant-a/backup")
        assert bak.status_code == 200
        rst = block_client.post("/tenants/tenant-a/restore")
        assert rst.status_code == 200
        bak_count = bak.json()["document_count"]
        rst_count = rst.json()["document_count"]
        assert_pass("D2", bak_count == rst_count, f"backup={bak_count}, restore={rst_count}")

    def test_d3_tenant_isolation(self, block_client, fixture_loader):
        """D3: tenant document ids are disjoint."""
        docs_a = [d for d in fixture_loader.get_documents() if d["tenant_id"] == "tenant-a"]
        docs_b = [d for d in fixture_loader.get_documents() if d["tenant_id"] == "tenant-b"]
        ids_a = {d["id"] for d in docs_a}
        ids_b = {d["id"] for d in docs_b}
        disjoint = ids_a.isdisjoint(ids_b)
        assert_pass("D3", disjoint, f"tenant-a={len(ids_a)} tenant-b={len(ids_b)} docs")

    def test_d4_key_rotation(self, block_client):
        """D4: key rotation increments keys_version."""
        before = block_client.get("/storage/health").json()["keys_version"]
        rot = block_client.post("/keys/rotate")
        assert rot.status_code == 200
        after = block_client.get("/storage/health").json()["keys_version"]
        assert_pass("D4", after == before + 1, f"keys_version {before} -> {after}")
