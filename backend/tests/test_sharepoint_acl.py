"""SharePoint ACL mirroring: Graph permissions → IdentityHint → same shape as Drive."""

from __future__ import annotations

import pytest

from app.core.models import PermissionLevel
from app.normalizer.strategies.sharepoint import SharePointNormalizer
from app.identity.resolver import MIRROR_BIND_SOURCES
from app.acl.compiler import _granted_via
from app.acl.filter import _normalize_document_id
from app.services.indexer import index_acl_terms
from app.storage.canonical_repo import _document_id_aliases, _source_type_from_document_id


def test_sharepoint_is_mirror_bind_source():
    assert "sharepoint" in MIRROR_BIND_SOURCES


def test_sharepoint_granted_via():
    assert _granted_via("sharepoint") == "sharepoint_share"


def test_sharepoint_dual_id_prefix_stripped():
    assert (
        _normalize_document_id("sharepoint_b!drive:01ITEM")
        == "b!drive:01ITEM"
    )


def test_extract_permission_hints_users_only():
    raw = {
        "id": "drive1:item1",
        "permissions": [
            {
                "roles": ["owner"],
                "grantedToV2": {
                    "user": {
                        "id": "u1",
                        "email": "owner@contoso.com",
                        "displayName": "Owner",
                    }
                },
            },
            {
                "roles": ["read"],
                "grantedToV2": {
                    "user": {
                        "id": "u2",
                        "email": "reader@contoso.com",
                    }
                },
            },
            {
                "roles": ["read"],
                "grantedToV2": {"group": {"id": "g1", "displayName": "Team"}},
            },
            {
                "roles": ["read"],
                "link": {"scope": "anonymous"},
            },
        ],
    }
    hints = SharePointNormalizer().extract_permission_hints(raw)
    emails = sorted(h.email for h, _level in hints)
    assert emails == ["owner@contoso.com", "reader@contoso.com"]
    levels = {h.email: level for h, level in hints}
    assert levels["owner@contoso.com"] == PermissionLevel.OWNER
    assert levels["reader@contoso.com"] == PermissionLevel.READ


def test_extract_permission_hints_falls_back_to_created_by():
    raw = {
        "id": "drive1:item1",
        "permissions": [],
        "createdBy": {"user": {"email": "creator@contoso.com", "id": "c1"}},
    }
    hints = SharePointNormalizer().extract_permission_hints(raw)
    assert len(hints) == 1
    hint, level = hints[0]
    assert hint.email == "creator@contoso.com"
    assert level == PermissionLevel.OWNER


def test_index_acl_terms_merges_extra_acl_with_mirrored_permissions():
    terms = index_acl_terms(
        ["user:member-uuid"],
        ["user:admin-uuid"],
    )
    assert "user:member-uuid" in terms
    assert "member-uuid" in terms
    assert "user:admin-uuid" in terms
    assert "admin-uuid" in terms


def test_sharepoint_document_id_aliases_include_prefix():
    aliases = _document_id_aliases("b!drive:01ITEM")
    assert "sharepoint_b!drive:01ITEM" in aliases
    stripped = _document_id_aliases("sharepoint_b!drive:01ITEM")
    assert "b!drive:01ITEM" in stripped
    assert _source_type_from_document_id("sharepoint_b!drive:01ITEM") == "sharepoint"


@pytest.mark.asyncio
async def test_extract_text_prefers_hydrated_content():
    raw = {
        "name": "file.docx",
        "_extracted_text": "Indexed SharePoint body text",
    }
    text = await SharePointNormalizer().extract_text(raw)
    assert "Indexed SharePoint body text" in text


@pytest.mark.asyncio
async def test_owner_can_read_sharepoint_doc_with_empty_acl_entries():
    from datetime import datetime, timezone
    from uuid import uuid4

    from app.core.models import CanonicalDocument
    from app.storage.canonical_repo import CanonicalRepo

    tenant = uuid4()
    owner = uuid4()
    other = uuid4()
    repo = CanonicalRepo(use_memory=True)
    doc_id = "sharepoint_7277ae:item"
    await repo.upsert_document(
        CanonicalDocument(
            id=doc_id,
            source_type="sharepoint",
            source_id="7277ae:item",
            tenant_id=tenant,
            title="Getting started with OneDrive.pdf",
            content="x",
            url="",
            mime_type="application/pdf",
            detected_mime_type="application/pdf",
            mime_mismatch=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            source_updated_at=datetime.now(timezone.utc),
            owner_principal_id=owner,
            structured_metadata={},
            parent_ids=[],
        )
    )
    await repo.replace_acl_entries(doc_id, [])
    assert await repo.principal_can_read_document(tenant, owner, "7277ae:item") is True
    assert await repo.principal_can_read_document(tenant, other, "7277ae:item") is False
