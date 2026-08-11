"""K1 — ACL re-check on every read; no caching after revoke."""

from __future__ import annotations

import pytest

from tests.conftest import make_bearer

TENANT = "tenant-k"
DOC_ID = "doc-acl-k1"
USER_A = "user-a"
USER_B = "user-b"


@pytest.mark.asyncio
async def test_k1_allow_then_deny_after_revoke(k_app):
    client, store, acl, _app = k_app

    store.upsert(
        TENANT,
        DOC_ID,
        title="ACL Recheck Doc",
        body="Secret body visible only while allowed.",
        owner_principal_id=USER_A,
        created_at="2026-08-10T12:00:00Z",
        updated_at="2026-08-11T10:00:00Z",
        acl_entries=[USER_A],
    )
    acl.grant(TENANT, DOC_ID, USER_A)
    # User B never granted

    # User A allowed
    resp_a = await client.get(
        f"/api/v1/document/{DOC_ID}",
        headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
    )
    assert resp_a.status_code == 200, resp_a.text
    assert resp_a.json()["document_id"] == DOC_ID
    assert "Secret body" in resp_a.json()["body"]

    # User B denied
    resp_b = await client.get(
        f"/api/v1/document/{DOC_ID}",
        headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_B)}"},
    )
    assert resp_b.status_code == 403

    # Revoke A — subsequent reads must be denied (no cache)
    acl.revoke(TENANT, DOC_ID, USER_A)
    calls_before = acl.call_count

    denied = 0
    for _ in range(10):
        resp = await client.get(
            f"/api/v1/document/{DOC_ID}",
            headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
        )
        if resp.status_code == 403:
            denied += 1
        else:
            pytest.fail(f"Expected 403 after revoke, got {resp.status_code}: {resp.text}")

    assert denied == 10, "100% of post-revocation requests must be denied"
    assert acl.call_count - calls_before == 10, "ACL must be re-checked every request (no cache)"


@pytest.mark.asyncio
async def test_k1_missing_token_401(k_app):
    client, store, acl, _app = k_app
    # Force non-test default path by sending empty Authorization intentionally
    # In environment=test, missing token returns stub user — so send invalid JWT shape
    from app.config import settings

    prev = settings.environment
    settings.environment = "production"
    try:
        resp = await client.get(f"/api/v1/document/{DOC_ID}")
        assert resp.status_code == 401
    finally:
        settings.environment = prev


@pytest.mark.asyncio
async def test_k1_not_found_404(k_app):
    client, store, acl, _app = k_app
    acl.grant(TENANT, "missing-doc", USER_A)
    resp = await client.get(
        "/api/v1/document/missing-doc",
        headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
    )
    assert resp.status_code == 404
