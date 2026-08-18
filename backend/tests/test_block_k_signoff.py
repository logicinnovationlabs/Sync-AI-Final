"""
Block K: Document Reader - Comprehensive Test Suite

Tests all three requirements:
- K1: ACL re-check on every read (no caching)
- K2: Streaming for large documents (>10MB)
- K3: Structure preservation (headings, tables, code blocks)
"""

from __future__ import annotations

import tracemalloc
import pytest

from tests.conftest import make_bearer

# Test constants
TENANT = "tenant-k"
USER_A = "user-a"
USER_B = "user-b"
LARGE_SIZE = 10 * 1024 * 1024 + 64 * 1024


# ============================================================================
# K1: ACL Re-check Tests
# ============================================================================

@pytest.mark.asyncio
async def test_k1_allow_then_deny_after_revoke(k_app):
    """K1: Verify ACL is re-checked on every read with no caching after revoke."""
    client, store, acl, _app = k_app
    doc_id = "doc-acl-k1"

    await store.upsert(
        TENANT,
        doc_id,
        title="ACL Recheck Doc",
        body="Secret body visible only while allowed.",
        owner_principal_id=USER_A,
        created_at="2026-08-10T12:00:00Z",
        updated_at="2026-08-11T10:00:00Z",
        acl_entries=[USER_A],
    )
    acl.grant(TENANT, doc_id, USER_A)

    # User A allowed
    resp_a = await client.get(
        f"/document/{doc_id}",
        headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
    )
    assert resp_a.status_code == 200, resp_a.text
    assert resp_a.json()["document_id"] == doc_id
    assert "Secret body" in resp_a.json()["body"]

    # User B denied
    resp_b = await client.get(
        f"/document/{doc_id}",
        headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_B)}"},
    )
    assert resp_b.status_code == 403

    # Revoke A — subsequent reads must be denied (no cache)
    acl.revoke(TENANT, doc_id, USER_A)
    calls_before = acl.call_count

    denied = 0
    for _ in range(10):
        resp = await client.get(
            f"/document/{doc_id}",
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
    """K1: Missing auth token returns 401."""
    client, store, acl, _app = k_app
    doc_id = "doc-missing-token"
    
    from app.core.config import settings
    prev = settings.environment
    settings.environment = "production"
    
    try:
        resp = await client.get(f"/document/{doc_id}")
        assert resp.status_code == 401
    finally:
        settings.environment = prev


@pytest.mark.asyncio
async def test_k1_not_found_404(k_app):
    """K1: Non-existent document returns 404."""
    client, store, acl, _app = k_app
    
    acl.grant(TENANT, "missing-doc", USER_A)
    resp = await client.get(
        "/document/missing-doc",
        headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
    )
    assert resp.status_code == 404


# ============================================================================
# K2: Streaming Tests
# ============================================================================

@pytest.mark.asyncio
async def test_k2_streams_large_document(k_app):
    """K2: Large documents (>10MB) are streamed with bounded memory."""
    client, store, acl, _app = k_app
    doc_id = "doc-large-k2"

    from app.core.config import settings
    from app.services.document_reader import stream_document_json

    prev_threshold = settings.stream_threshold_bytes
    settings.stream_threshold_bytes = 10 * 1024 * 1024

    body = ("A" * 1024) * (LARGE_SIZE // 1024)
    assert len(body) > 10 * 1024 * 1024

    meta = await store.upsert(
        TENANT,
        doc_id,
        title="Large Streaming Doc",
        body=body,
        owner_principal_id=USER_A,
        created_at="2026-08-10T12:00:00Z",
        updated_at="2026-08-11T10:00:00Z",
        structured_metadata={
            "headings": ["Huge"],
            "tables": [],
            "code_blocks": [],
            "language": "en",
        },
    )
    acl.grant(TENANT, doc_id, USER_A)

    resp = await client.get(
        f"/document/{doc_id}",
        headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("x-document-streaming") == "1"
    assert resp.headers.get("content-type", "").startswith("application/json")

    data = resp.json()
    assert data["document_id"] == doc_id
    assert data["title"] == "Large Streaming Doc"
    assert len(data["body"]) == len(body)
    assert data["body"].startswith("AAAA")
    assert data["body"].endswith("AAAA")

    # Verify memory stays bounded when chunks are not retained
    tracemalloc.start()
    baseline = tracemalloc.get_traced_memory()[0]
    total = 0
    peak_seen = 0
    
    async for chunk in stream_document_json(
        store,
        meta["object_key"],
        doc_id,
        TENANT,
        {
            "title": meta["title"],
            "owner_principal_id": USER_A,
            "created_at": meta["created_at"],
            "updated_at": meta["updated_at"],
        },
        meta["structured_metadata"],
    ):
        total += len(chunk)
        _current, peak = tracemalloc.get_traced_memory()
        peak_seen = max(peak_seen, peak)

    growth = peak_seen - baseline
    tracemalloc.stop()
    settings.stream_threshold_bytes = prev_threshold

    assert total > len(body), "stream should emit metadata + body"
    assert growth < 5 * 1024 * 1024, (
        f"Stream generator peak growth {growth} not bounded "
        f"(want <5MB while streaming {len(body)}-byte body)"
    )


@pytest.mark.asyncio
async def test_k2_small_document_not_streamed(k_app):
    """K2: Small documents are returned in full (not streamed)."""
    client, store, acl, _app = k_app
    
    await store.upsert(
        TENANT,
        "doc-small",
        title="Small",
        body="hello world",
        owner_principal_id=USER_A,
    )
    acl.grant(TENANT, "doc-small", USER_A)

    resp = await client.get(
        "/document/doc-small",
        headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("x-document-streaming") is None
    assert resp.json()["body"] == "hello world"


# ============================================================================
# K3: Structure Preservation Tests
# ============================================================================

@pytest.fixture
def structured_doc():
    """Fixture providing a structured document with headings, tables, code blocks."""
    return {
        "tenant_id": TENANT,
        "document_id": "doc-structured-k3",
        "owner_principal_id": USER_A,
        "title": "Structured Document",
        "body": "# Heading 1\n\nParagraph text.\n\n## Heading 2\n\n| Col1 | Col2 |\n|------|------|\n| A | B |\n\n```python\ndef hello():\n    print('world')\n```",
        "structured_metadata": {
            "headings": ["Heading 1", "Heading 2"],
            "tables": [{"rows": 2, "cols": 2}],
            "code_blocks": [{"language": "python", "lines": 2}],
            "language": "en",
        },
        "created_at": "2026-08-10T12:00:00Z",
        "updated_at": "2026-08-11T10:00:00Z",
        "hidden_fields": [],
        "visibility_mode": "acl",
    }


@pytest.mark.asyncio
async def test_k3_structure_fidelity(k_app, structured_doc):
    """K3: Verify document structure (headings, tables, code blocks) is preserved 100%."""
    client, store, acl, _app = k_app

    tenant = structured_doc["tenant_id"]
    doc_id = structured_doc["document_id"]
    principal = structured_doc["owner_principal_id"]
    expected_structured = structured_doc["structured_metadata"]
    expected_body = structured_doc["body"]

    await store.upsert(
        tenant,
        doc_id,
        title=structured_doc["title"],
        body=expected_body,
        structured_metadata=expected_structured,
        owner_principal_id=principal,
        created_at=structured_doc["created_at"],
        updated_at=structured_doc["updated_at"],
        hidden_fields=structured_doc.get("hidden_fields", []),
        visibility_mode=structured_doc.get("visibility_mode", "acl"),
        extra={"secret_field": "SHOULD_REDACT_FOR_NON_OWNER"},
    )
    acl.grant(tenant, doc_id, principal)

    resp = await client.get(
        f"/document/{doc_id}",
        headers={"Authorization": f"Bearer {make_bearer(tenant, principal)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Verify all fields preserved
    assert data["document_id"] == doc_id
    assert data["tenant_id"] == tenant
    assert data["title"] == structured_doc["title"]
    assert data["body"] == expected_body
    assert data["structured_metadata"] == expected_structured
    assert data["structured_metadata"]["headings"] == expected_structured["headings"]
    assert data["structured_metadata"]["tables"] == expected_structured["tables"]
    assert data["structured_metadata"]["code_blocks"] == expected_structured["code_blocks"]
    assert data["structured_metadata"]["language"] == expected_structured["language"]


@pytest.mark.asyncio
async def test_k3_redacts_hidden_fields_for_non_owner(k_app, structured_doc):
    """K3: Hidden fields are redacted for non-owner readers."""
    client, store, acl, _app = k_app

    tenant = structured_doc["tenant_id"]
    doc_id = "doc-redact-k3"
    owner = structured_doc["owner_principal_id"]
    reader = "user-reader"

    await store.upsert(
        tenant,
        doc_id,
        title="Redaction Doc",
        body="# Title\n\nVisible body",
        structured_metadata={
            "headings": ["Title"],
            "tables": [],
            "code_blocks": [],
            "language": "en",
        },
        owner_principal_id=owner,
        visibility_mode="redacted",
        hidden_fields=["secret_field"],
        extra={"secret_field": "TOP_SECRET"},
    )
    acl.grant(tenant, doc_id, reader)

    resp = await client.get(
        f"/document/{doc_id}",
        headers={"Authorization": f"Bearer {make_bearer(tenant, reader)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    
    # Secret field should be redacted
    assert "secret_field" not in data
    # But structure should be preserved
    assert data["structured_metadata"]["headings"] == ["Title"]
