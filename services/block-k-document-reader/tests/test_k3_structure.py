"""K3 — Structure fidelity: headings, tables, code blocks preserved 100%."""

from __future__ import annotations

import pytest

from tests.conftest import make_bearer


@pytest.mark.asyncio
async def test_k3_structure_fidelity(k_app, structured_doc):
    client, store, acl, _app = k_app

    tenant = structured_doc["tenant_id"]
    doc_id = structured_doc["document_id"]
    principal = structured_doc["owner_principal_id"]
    expected_structured = structured_doc["structured_metadata"]
    expected_body = structured_doc["body"]

    store.upsert(
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
        f"/api/v1/document/{doc_id}",
        headers={"Authorization": f"Bearer {make_bearer(tenant, principal)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

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
    client, store, acl, _app = k_app

    tenant = structured_doc["tenant_id"]
    doc_id = "doc-redact-k3"
    owner = structured_doc["owner_principal_id"]
    reader = "user-reader"

    store.upsert(
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
        f"/api/v1/document/{doc_id}",
        headers={"Authorization": f"Bearer {make_bearer(tenant, reader)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "secret_field" not in data
    assert data["structured_metadata"]["headings"] == ["Title"]
