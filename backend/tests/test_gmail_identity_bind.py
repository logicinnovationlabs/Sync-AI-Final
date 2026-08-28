"""Gmail mailbox bind, ghost-owner skip, delete ACL, poll enqueue."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.acl.compiler import ACLCompiler
from app.acl.container_service import ContainerService
from app.core.models import ACLEntry, CanonicalDocument, IdentityHint, PermissionLevel, Principal
from app.identity.matchers.email_matcher import EmailMatcher
from app.identity.matchers.username_matcher import UsernameMatcher
from app.identity.resolver import IdentityResolver
from app.normalizer.strategies.google_gmail import GoogleGmailNormalizer
from app.storage.canonical_repo import CanonicalRepo, bind_pending_drive_shares


def _now():
    return datetime.now(timezone.utc)


def _gmail_doc(tenant_id, doc_id="google_gmail_msg1"):
    return CanonicalDocument(
        id=doc_id,
        source_type="google_gmail",
        source_id="msg1",
        tenant_id=tenant_id,
        title="Mail",
        content="body",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        created_at=_now(),
        updated_at=_now(),
        source_updated_at=_now(),
    )


@pytest.mark.asyncio
async def test_gmail_mailbox_unmatched_queues_not_ghost():
    repo = CanonicalRepo(use_memory=True)
    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    tenant_id = uuid4()
    resolved = await resolver.resolve(
        IdentityHint(
            source_type="google_gmail",
            external_id="admin@synq.dev",
            email="admin@synq.dev",
        ),
        tenant_id,
        document_id="google_gmail_msg1",
    )
    assert resolved.is_pending is True
    assert resolved.principal_id is None
    assert await repo.get_principal_by_email("admin@synq.dev", tenant_id) is None


@pytest.mark.asyncio
async def test_gmail_mailbox_binds_users_principal_id():
    repo = CanonicalRepo(use_memory=True)
    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    compiler = ACLCompiler(resolver, ContainerService(repo), repo)
    tenant_id = uuid4()
    login_id = uuid4()
    repo.register_login_user(tenant_id, "admin@synq.dev", login_id)
    doc = _gmail_doc(tenant_id)
    entries = await compiler.compile(
        doc,
        [
            (
                IdentityHint(
                    source_type="google_gmail",
                    external_id="admin@synq.dev",
                    email="admin@synq.dev",
                ),
                PermissionLevel.OWNER,
            )
        ],
        tenant_id,
    )
    assert len(entries) == 1
    assert entries[0].principal_id == login_id
    assert entries[0].granted_via == "gmail_mailbox"


@pytest.mark.asyncio
async def test_gmail_ghost_principal_rebinds_on_login_drain():
    repo = CanonicalRepo(use_memory=True)
    tenant_id = uuid4()
    ghost_id = uuid4()
    login_id = uuid4()
    doc = _gmail_doc(tenant_id)
    await repo.upsert_document(doc)
    await repo.create_principal(
        Principal(
            id=ghost_id,
            tenant_id=tenant_id,
            email="admin@synq.dev",
            name="Admin",
            source_identities={"google_gmail": "admin@synq.dev"},
            created_at=_now(),
            updated_at=_now(),
        )
    )
    await repo.insert_acl_entry(
        ACLEntry(
            document_id=doc.id,
            principal_id=ghost_id,
            permission=PermissionLevel.OWNER,
            granted_via="gmail_mailbox",
            is_deny=False,
            source_type="google_gmail",
            tenant_id=tenant_id,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    repo.register_login_user(tenant_id, "admin@synq.dev", login_id)

    class _Session:
        pass

    with patch("app.storage.canonical_repo.CanonicalRepo", return_value=repo), patch(
        "app.services.indexer.indexer.reindex_by_ids", new=AsyncMock()
    ):
        drained = await bind_pending_drive_shares(
            _Session(), tenant_id, "admin@synq.dev", login_id
        )
    assert doc.id in drained
    entries = await repo.get_acl_entries(doc.id)
    assert entries[0].principal_id == login_id


def test_gmail_placeholder_mailbox_emits_no_acl_hint():
    hints = GoogleGmailNormalizer().extract_permission_hints(
        {"payload": {"headers": []}, "_mailbox_email": "user@example.com"}
    )
    assert hints == []


@pytest.mark.asyncio
async def test_delete_drops_acl_aliases():
    repo = CanonicalRepo(use_memory=True)
    tenant_id = uuid4()
    doc = _gmail_doc(tenant_id, "google_gmail_abc")
    await repo.upsert_document(doc)
    await repo.insert_acl_entry(
        ACLEntry(
            document_id=doc.id,
            principal_id=uuid4(),
            permission=PermissionLevel.OWNER,
            granted_via="gmail_mailbox",
            is_deny=False,
            source_type="google_gmail",
            tenant_id=tenant_id,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    await repo.delete_documents_and_acls(["abc"], tenant_id)
    assert await repo.get_document(doc.id) is None
    assert await repo.get_acl_entries(doc.id) == []


def test_poll_drive_acl_delta_enqueues_webhook_task():
    from app.workers.drive_acl_poll import enqueue_drive_acl_poll

    called = []
    result = enqueue_drive_acl_poll(["tenant-a", "tenant-b"], called.append)
    assert result["enqueued"] == 2
    assert called == ["tenant-a", "tenant-b"]
