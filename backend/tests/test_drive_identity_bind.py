"""Drive-share identity bind: pending queue, login drain, reader fail-closed.

Does not modify test_identity_resolver.py cases (those omit document_id and
keep create-on-miss).
"""

from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest

from app.acl.compiler import ACLCompiler
from app.acl.container_service import ContainerService
from app.core.models import (
    CanonicalDocument,
    IdentityHint,
    PermissionLevel,
    ACLEntry,
)
from app.identity.matchers.email_matcher import EmailMatcher
from app.identity.matchers.username_matcher import UsernameMatcher
from app.identity.resolver import IdentityResolver
from app.normalizer.strategies.google_drive import GoogleDriveNormalizer
from app.services.document_reader.acl_checker import PostgresACLChecker
from app.storage.canonical_repo import CanonicalRepo, bind_pending_drive_shares


def _now():
    return datetime.now(timezone.utc)


def _doc(tenant_id, doc_id="google_drive_file1"):
    return CanonicalDocument(
        id=doc_id,
        source_type="google_drive",
        source_id="file1",
        tenant_id=tenant_id,
        title="Shared",
        content="body",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        created_at=_now(),
        updated_at=_now(),
        source_updated_at=_now(),
    )


@pytest.mark.asyncio
async def test_drive_share_unmatched_email_queues_not_ghost_principal():
    repo = CanonicalRepo(use_memory=True)
    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    tenant_id = uuid4()
    hint = IdentityHint(
        source_type="google_drive",
        external_id="perm_1",
        email="member1@gmail.com",
        name="Member",
    )

    resolved = await resolver.resolve(
        hint, tenant_id, document_id="google_drive_file1"
    )

    assert resolved.is_pending is True
    assert resolved.matched_on == "pending"
    assert resolved.principal_id is None
    assert await repo.get_principal_by_email("member1@gmail.com", tenant_id) is None
    assert ("google_drive_file1",) == (
        tuple(
            row["document_id"]
            for row in repo._pending_identity.values()
            if row["shared_email"] == "member1@gmail.com"
        )
    )


@pytest.mark.asyncio
async def test_drive_share_without_document_id_still_creates_principal():
    """Existing identity_resolver contract: omit document_id → create-on-miss."""
    repo = CanonicalRepo(use_memory=True)
    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    tenant_id = uuid4()
    hint = IdentityHint(
        source_type="google_drive",
        external_id="user_1",
        email="alice@example.com",
        name="Alice Smith",
    )
    resolved = await resolver.resolve(hint, tenant_id)
    assert resolved.principal_id
    assert resolved.matched_on == "new"
    assert resolved.is_pending is False


@pytest.mark.asyncio
async def test_compiler_skips_acl_row_for_pending_drive_share():
    repo = CanonicalRepo(use_memory=True)
    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    compiler = ACLCompiler(resolver, ContainerService(repo), repo)
    tenant_id = uuid4()
    doc = _doc(tenant_id)
    hints = [
        (
            IdentityHint(
                source_type="google_drive",
                external_id="perm_1",
                email="member1@gmail.com",
            ),
            PermissionLevel.READ,
        )
    ]
    entries = await compiler.compile(doc, hints, tenant_id)
    assert entries == []
    queued = [
        row
        for row in repo._pending_identity.values()
        if row["shared_email"] == "member1@gmail.com"
    ]
    assert len(queued) == 1


@pytest.mark.asyncio
async def test_drain_writes_acl_under_users_principal_id():
    repo = CanonicalRepo(use_memory=True)
    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    tenant_id = uuid4()
    principal_id = uuid4()
    doc = _doc(tenant_id)
    await repo.upsert_document(doc)
    await resolver.resolve(
        IdentityHint(
            source_type="google_drive",
            external_id="perm_1",
            email="member1@gmail.com",
        ),
        tenant_id,
        document_id=doc.id,
    )

    repo.register_login_user(tenant_id, "member1@gmail.com", principal_id)
    drained = await repo.drain_pending_identity_queue(
        tenant_id, "member1@gmail.com", principal_id
    )
    assert doc.id in drained
    entries = await repo.get_acl_entries(doc.id)
    assert len(entries) == 1
    assert entries[0].principal_id == principal_id
    assert entries[0].granted_via == "drive_share"
    assert entries[0].is_deny is False
    queued = [
        row
        for row in repo._pending_identity.values()
        if row["shared_email"] == "member1@gmail.com"
    ]
    assert queued[0]["resolved_at"] is not None
    assert queued[0]["resolved_principal_id"] == principal_id


@pytest.mark.asyncio
async def test_bind_pending_drive_shares_reindexes_only_resolved_docs():
    repo = CanonicalRepo(use_memory=True)
    resolver = IdentityResolver([EmailMatcher(), UsernameMatcher()], repo)
    tenant_id = uuid4()
    principal_id = uuid4()
    doc = _doc(tenant_id)
    await repo.upsert_document(doc)
    await resolver.resolve(
        IdentityHint(
            source_type="google_drive",
            external_id="perm_1",
            email="member1@gmail.com",
        ),
        tenant_id,
        document_id=doc.id,
    )
    repo.register_login_user(tenant_id, "member1@gmail.com", principal_id)

    class _Session:
        pass

    with patch(
        "app.storage.canonical_repo.CanonicalRepo",
        return_value=repo,
    ), patch("app.services.indexer.indexer.reindex_by_ids", new_callable=AsyncMock) as reindex:
        ids = await bind_pending_drive_shares(
            _Session(), tenant_id, "member1@gmail.com", principal_id
        )
    assert doc.id in ids
    reindex.assert_awaited()
    called_ids = reindex.await_args.args[1]
    assert called_ids == [doc.id]


@pytest.mark.asyncio
async def test_anyone_permission_does_not_create_hint():
    normalizer = GoogleDriveNormalizer()
    hints = normalizer.extract_permission_hints(
        {
            "id": "file_public",
            "permissions": [
                {"type": "anyone", "role": "reader", "id": "pa"},
                {
                    "type": "user",
                    "emailAddress": "member1@gmail.com",
                    "role": "reader",
                    "id": "pu",
                },
            ],
            "owners": [{"emailAddress": "owner@x.com"}],
        }
    )
    emails = [h.email for h, _ in hints]
    assert "*" not in emails
    assert "member1@gmail.com" in emails


@pytest.mark.asyncio
async def test_postgres_acl_checker_fail_closed_and_deny_wins():
    repo = CanonicalRepo(use_memory=True)
    checker = PostgresACLChecker(repo=repo)
    tenant_id = uuid4()
    principal_id = uuid4()
    doc_id = "google_drive_file1"

    assert await checker.is_allowed(str(tenant_id), str(principal_id), doc_id) is False

    now = _now()
    await repo.insert_acl_entry(
        ACLEntry(
            document_id=doc_id,
            principal_id=principal_id,
            permission=PermissionLevel.READ,
            granted_via="drive_share",
            is_deny=False,
            source_type="google_drive",
            tenant_id=tenant_id,
            created_at=now,
            updated_at=now,
        )
    )
    assert await checker.is_allowed(str(tenant_id), str(principal_id), doc_id) is True

    await repo.insert_acl_entry(
        ACLEntry(
            document_id=doc_id,
            principal_id=principal_id,
            permission=PermissionLevel.NONE,
            granted_via="drive_share",
            is_deny=True,
            source_type="google_drive",
            tenant_id=tenant_id,
            created_at=now,
            updated_at=now,
        )
    )
    assert await checker.is_allowed(str(tenant_id), str(principal_id), doc_id) is False
