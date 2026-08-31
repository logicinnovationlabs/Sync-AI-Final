"""Tests for connector disconnect document and vector purge."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

import pytest
from app.core.models import CanonicalDocument, ACLEntry, PermissionLevel
from app.storage.canonical_repo import CanonicalRepo
from app.workers.tasks import purge_connector_documents_task


@pytest.mark.asyncio
async def test_canonical_repo_delete_documents_by_source():
    """Verify CanonicalRepo delete_documents_by_source purges only matching source & tenant."""
    repo = CanonicalRepo(use_memory=True)
    tenant_1 = uuid4()
    tenant_2 = uuid4()
    now = datetime.now(timezone.utc)

    doc_drive_1 = CanonicalDocument(
        id="drive-1",
        source_type="google_drive",
        source_id="file-1",
        tenant_id=tenant_1,
        title="Drive File 1",
        content="Hello Drive 1",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        created_at=now,
        updated_at=now,
        source_updated_at=now,
    )
    doc_drive_2 = CanonicalDocument(
        id="drive-2",
        source_type="google_drive",
        source_id="file-2",
        tenant_id=tenant_1,
        title="Drive File 2",
        content="Hello Drive 2",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        created_at=now,
        updated_at=now,
        source_updated_at=now,
    )
    doc_gmail_1 = CanonicalDocument(
        id="gmail-1",
        source_type="google_gmail",
        source_id="msg-1",
        tenant_id=tenant_1,
        title="Gmail Message 1",
        content="Hello Gmail 1",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        created_at=now,
        updated_at=now,
        source_updated_at=now,
    )
    doc_tenant2 = CanonicalDocument(
        id="t2-drive-1",
        source_type="google_drive",
        source_id="file-t2",
        tenant_id=tenant_2,
        title="Tenant 2 Drive File",
        content="Hello T2",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        created_at=now,
        updated_at=now,
        source_updated_at=now,
    )

    await repo.upsert_document(doc_drive_1)
    await repo.upsert_document(doc_drive_2)
    await repo.upsert_document(doc_gmail_1)
    await repo.upsert_document(doc_tenant2)

    acl_drive = ACLEntry(
        document_id="drive-1",
        permission=PermissionLevel.READ,
        granted_via="direct",
        source_type="google_drive",
        tenant_id=tenant_1,
        created_at=now,
        updated_at=now,
    )
    acl_gmail = ACLEntry(
        document_id="gmail-1",
        permission=PermissionLevel.READ,
        granted_via="direct",
        source_type="google_gmail",
        tenant_id=tenant_1,
        created_at=now,
        updated_at=now,
    )
    await repo.replace_acl_entries("drive-1", [acl_drive])
    await repo.replace_acl_entries("gmail-1", [acl_gmail])

    # Delete google_drive for tenant_1
    deleted_ids = await repo.delete_documents_by_source("google_drive", tenant_1)
    assert set(deleted_ids) == {"drive-1", "drive-2"}

    # Assert drive docs deleted
    assert await repo.get_document("drive-1") is None
    assert await repo.get_document("drive-2") is None

    # Assert gmail docs & tenant 2 docs remain intact
    assert await repo.get_document("gmail-1") is not None
    assert await repo.get_document("t2-drive-1") is not None

    # Assert drive ACLs deleted, gmail ACLs preserved
    acls_drive = await repo.get_acl_entries("drive-1")
    assert len(acls_drive) == 0
    acls_gmail = await repo.get_acl_entries("gmail-1")
    assert len(acls_gmail) == 1


@pytest.mark.asyncio
async def test_indexer_delete_by_source():
    """Verify Indexer.delete_by_source coordinates DB deletion and Qdrant vector deletion."""
    from app.services.indexer import Indexer

    mock_session = AsyncMock()
    mock_factory = MagicMock(return_value=mock_session)

    mock_routing = MagicMock()
    mock_routing.tenant_id = uuid4()
    mock_routing.db_host = "localhost"
    mock_routing.db_name = "test"
    mock_routing.db_user = "user"
    mock_routing.db_password = "pw"

    mock_repo = AsyncMock()
    mock_repo.delete_documents_by_source = AsyncMock(return_value=["doc-1", "doc-2"])

    indexer_inst = Indexer()
    indexer_inst.qdrant = MagicMock()
    indexer_inst.qdrant.delete_by_ids = AsyncMock()

    with patch("app.services.tenant_resolver.tenant_resolver.resolve", AsyncMock(return_value=mock_routing)), \
         patch("app.storage.tenant_db.tenant_db_manager.get_session_factory", return_value=mock_factory), \
         patch("app.storage.canonical_repo.CanonicalRepo", return_value=mock_repo):

        deleted_count = await indexer_inst.delete_by_source(str(mock_routing.tenant_id), "google_drive")

        assert deleted_count == 2
        mock_repo.delete_documents_by_source.assert_awaited_once_with("google_drive", mock_routing.tenant_id)
        indexer_inst.qdrant.delete_by_ids.assert_awaited_once_with(["doc-1", "doc-2"], tenant_id=str(mock_routing.tenant_id))


def test_purge_connector_documents_task_is_importable():
    """Ensure celery task is registered and callable."""
    assert callable(purge_connector_documents_task.delay)
    assert purge_connector_documents_task.name == "app.workers.tasks.purge_connector_documents_task"


def test_purge_connector_documents_task_executes():
    """Ensure Celery task executes indexer.delete_by_source."""
    tenant_id = str(uuid4())
    source_type = "onedrive"

    with patch("app.services.indexer.indexer.delete_by_source", AsyncMock(return_value=5)) as mock_del:
        res = purge_connector_documents_task(tenant_id, source_type)
        assert res["deleted_count"] == 5
        assert res["status"] == "purged"
        assert res["source_type"] == source_type
        assert res["tenant_id"] == tenant_id
