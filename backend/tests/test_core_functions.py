"""
Edge‑Case Tests for Core Components
===================================
Tests that go beyond the happy path – validates robustness under:
- Empty, malformed, or huge responses
- Permission quirks (empty, wildcard, malformed)
- Pagination with empty pages
- Deletion scenarios (delete, unshare, move)
- Metadata allowlist with unusual keys
- Unicode and special characters
- Token expiration and refresh
- Concurrent operations and tenant isolation

Run with:
    pytest tests/test_core_edge_cases.py -v
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.base_connector import UnifiedDocument
from app.services.indexer import Indexer
from app.services.registry import connector_registry
from app.connectors.google.services.drive_service import DriveConnector
from app.connectors.google.services.gmail_service import GmailConnector
from app.connectors.google.oauth import GoogleOAuthManager


def _bind_indexer_mocks(indexer, *, allowed_keys=None, embed_side_effect=None):
    mock_embed = MagicMock()
    mock_embed.get_dimension = MagicMock(return_value=768)
    if embed_side_effect is not None:
        mock_embed.embed_texts = AsyncMock(side_effect=embed_side_effect)
    else:
        mock_embed.embed_texts = AsyncMock(return_value=[[0.1] * 768])
    mock_qdrant = MagicMock()
    mock_qdrant.upsert_documents = AsyncMock()
    mock_registry = MagicMock()
    mock_registry.get_allowed_metadata_keys = MagicMock(
        return_value=list(allowed_keys or [])
    )
    indexer.embedding_service = mock_embed
    indexer.qdrant = mock_qdrant
    indexer.registry = mock_registry
    return mock_embed, mock_qdrant, mock_registry


# ---------- Fixtures (same as core_functions) ----------
class DictTokenStore:
    def __init__(self):
        self._data = {}
    def get_token(self, key: str):
        return self._data.get(key)
    def set_token(self, key: str, token_data: dict):
        self._data[key] = token_data

@pytest.fixture
def mock_token_store():
    store = DictTokenStore()
    store.set_token("google_test", {"access_token": "fake_token", "refresh_token": "fake_refresh"})
    return store

@pytest.fixture
def mock_oauth_manager():
    manager = MagicMock(spec=GoogleOAuthManager)
    manager.get_valid_token = AsyncMock(return_value="fake_token_12345")
    return manager

@pytest.fixture
def drive_connector(mock_token_store, mock_oauth_manager):
    config = {"tenant_id": "test_tenant", "client_id": "fake", "client_secret": "fake"}
    return DriveConnector(config, mock_token_store, oauth_manager=mock_oauth_manager)

@pytest.fixture
def gmail_connector(mock_token_store, mock_oauth_manager):
    config = {"tenant_id": "test_tenant", "client_id": "fake", "client_secret": "fake", "mailbox_email": "test@example.com"}
    return GmailConnector(config, mock_token_store, oauth_manager=mock_oauth_manager)


# ============================================================
# 1. EMPTY & MALFORMED RESPONSES
# ============================================================

@pytest.mark.asyncio
async def test_drive_transform_empty_list(drive_connector):
    """transform() must handle empty input gracefully."""
    docs = await drive_connector.transform([])
    assert docs == []

@pytest.mark.asyncio
async def test_drive_transform_missing_id(drive_connector):
    """transform() must skip documents without an ID."""
    raw = [{"name": "no_id_file", "mimeType": "text/plain"}]
    docs = await drive_connector.transform(raw)
    assert docs == []

@pytest.mark.asyncio
async def test_drive_transform_partial_fields(drive_connector):
    """transform() must set default/fallback values for missing fields."""
    raw = [{"id": "file1", "name": "Untitled"}]
    with patch.object(drive_connector, "_resolve_permissions", AsyncMock(return_value=["user:owner@x.com"])):
        docs = await drive_connector.transform(raw)
    doc = docs[0]
    assert doc.title == "Untitled"
    assert doc.content == "Untitled"  # fallback to name
    assert doc.url == "https://drive.google.com/file/d/file1"
    assert doc.permissions == ["user:owner@x.com"]
    # structured_metadata should have empty strings for missing fields
    assert doc.structured_metadata.get("mime_type") == ""
    assert doc.structured_metadata.get("file_extension") == ""


# ============================================================
# 2. PERMISSION EDGE CASES
# ============================================================

@pytest.mark.asyncio
async def test_drive_permissions_empty(drive_connector):
    """_resolve_permissions must return owner as fallback when permissions list is empty."""
    file = {"owners": [{"emailAddress": "owner@x.com"}]}
    perms = await drive_connector._resolve_permissions(file)
    assert perms == ["user:owner@x.com"]

@pytest.mark.asyncio
async def test_drive_permissions_deleted_user(drive_connector):
    """_resolve_permissions must skip deleted users."""
    file = {
        "permissions": [
            {"type": "user", "emailAddress": "deleted@x.com", "deleted": True},
            {"type": "user", "emailAddress": "active@x.com", "deleted": False},
        ],
        "owners": [{"emailAddress": "owner@x.com"}],
    }
    perms = await drive_connector._resolve_permissions(file)
    assert "user:deleted@x.com" not in perms
    assert "user:active@x.com" in perms

@pytest.mark.asyncio
async def test_drive_permissions_public(drive_connector):
    """'anyone' must not become a universal ACL; owner fallback still applies."""
    file = {
        "permissions": [{"type": "anyone", "emailAddress": ""}],
        "owners": [{"emailAddress": "owner@x.com"}],
    }
    perms = await drive_connector._resolve_permissions(file)
    assert "user:*" not in perms
    assert "user:owner@x.com" in perms

@pytest.mark.asyncio
async def test_drive_permissions_malformed_type(drive_connector):
    """_resolve_permissions must skip unknown types."""
    file = {
        "permissions": [{"type": "weird", "emailAddress": "x@x.com"}],
        "owners": [{"emailAddress": "owner@x.com"}],
    }
    perms = await drive_connector._resolve_permissions(file)
    assert "user:owner@x.com" in perms
    assert "user:x@x.com" not in perms


# ============================================================
# 3. PAGINATION EDGE CASES
# ============================================================

@pytest.mark.asyncio
async def test_drive_fetch_delta_empty_page(drive_connector):
    """fetch_delta must handle a page with no files and no next page token."""
    mock_client = AsyncMock()
    mock_client.list_files.return_value = {"files": [], "nextPageToken": None}
    drive_connector.drive_client = mock_client
    result = await drive_connector.fetch_delta(
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        cursor=None
    )
    assert result.documents == []
    assert result.has_more is False
    assert result.next_cursor is None

@pytest.mark.asyncio
async def test_drive_fetch_delta_cursor_only_no_files(drive_connector):
    """fetch_delta must correctly handle a cursor that returns no new files."""
    mock_client = AsyncMock()
    mock_client.list_files.return_value = {
        "files": [],
        "nextPageToken": "next_token_abc"  # Still has more pages, but empty
    }
    drive_connector.drive_client = mock_client
    result = await drive_connector.fetch_delta(
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        cursor="some_old_token"
    )
    assert result.documents == []
    assert result.has_more is True
    assert result.next_cursor == "next_token_abc"


# ============================================================
# 4. DELETION EDGE CASES
# ============================================================

@pytest.mark.asyncio
async def test_drive_fetch_deleted_ids_empty(drive_connector):
    """fetch_deleted_ids must handle empty change list."""
    mock_client = AsyncMock()
    mock_client.list_changes.return_value = {
        "changes": [],
        "newStartPageToken": "new_token"
    }
    drive_connector.drive_client = mock_client
    result = await drive_connector.fetch_deleted_ids(
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        cursor=None
    )
    assert result.deleted_ids == []
    assert result.has_more is False
    assert result.next_cursor == "new_token"

@pytest.mark.asyncio
async def test_drive_fetch_deleted_ids_mixed_types(drive_connector):
    """fetch_deleted_ids must only include truly deleted files (removed=True)."""
    mock_client = AsyncMock()
    mock_client.list_changes.return_value = {
        "changes": [
            {"fileId": "del1", "removed": True},
            {"fileId": "stay1", "removed": False, "file": {"id": "stay1"}},
            {"fileId": "del2", "removed": True},
        ],
        "newStartPageToken": "token"
    }
    drive_connector.drive_client = mock_client
    result = await drive_connector.fetch_deleted_ids(
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        cursor=None
    )
    assert result.deleted_ids == ["del1", "del2"]
    assert "stay1" not in result.deleted_ids


# ============================================================
# 5. METADATA ALLOWLIST EDGE CASES
# ============================================================

@pytest.mark.asyncio
async def test_indexer_allowlist_unusual_keys():
    """Indexer must strip metadata with special characters, null bytes, etc."""
    indexer = Indexer()
    mock_embed, mock_qdrant, mock_registry = _bind_indexer_mocks(
        indexer, allowed_keys=["safe_key"]
    )
    with patch.object(indexer, "_fanout_search_pipeline", new_callable=AsyncMock):
        doc = UnifiedDocument(
            id="test",
            title="T",
            content="C",
            source_type="google_drive",
            url="x",
            permissions=["user:a@x.com"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            source_updated_at=datetime.now(timezone.utc),
            structured_metadata={
                "safe_key": "ok",
                "bad\x00key": "should_be_removed",
                "key.with.dots": "should_be_removed",
                "": "empty_key_should_be_removed",
            }
        )
        await indexer.bulk_index([doc], "tenant")
        payload = mock_qdrant.upsert_documents.call_args[0][0][0]
        metadata = payload["structured_metadata"]
        assert "safe_key" in metadata
        assert "bad\x00key" not in metadata
        assert "key.with.dots" not in metadata
        assert "" not in metadata


# ============================================================
# 6. UNICODE & SPECIAL CHARACTERS
# ============================================================

@pytest.mark.asyncio
async def test_drive_transform_unicode(drive_connector):
    """transform must handle Unicode filenames and content."""
    raw = [{
        "id": "unicode_file",
        "name": "📄 文件.pdf",
        "mimeType": "application/pdf",
        "webViewLink": "https://x",
        "createdTime": "2026-01-01T00:00:00Z",
        "modifiedTime": "2026-01-01T00:00:00Z",
        "owners": [{"emailAddress": "owner@x.com"}],
    }]
    with patch.object(drive_connector, "_resolve_permissions", AsyncMock(return_value=["user:owner@x.com"])):
        docs = await drive_connector.transform(raw)
    assert docs[0].title == "📄 文件.pdf"
    assert docs[0].content == "📄 文件.pdf"  # content is still filename placeholder


# ============================================================
# 7. TOKEN EXPIRATION / REFRESH
# ============================================================

@pytest.mark.asyncio
async def test_drive_get_valid_token_refresh(drive_connector, mock_oauth_manager):
    """get_valid_token must call refresh when token is expired."""
    # Simulate expired token – first call raises, second returns new
    mock_oauth_manager.get_valid_token = AsyncMock(side_effect=[
        Exception("Token expired"),
        "new_token_123"
    ])
    token = await drive_connector.get_valid_token()
    assert token == "new_token_123"
    assert mock_oauth_manager.get_valid_token.call_count == 2


# ============================================================
# 8. TENANT ISOLATION (Indexer adds tenant_id)
# ============================================================

@pytest.mark.asyncio
async def test_indexer_tenant_isolation():
    """Indexer must attach tenant_id to every document payload."""
    indexer = Indexer()
    mock_embed, mock_qdrant, mock_registry = _bind_indexer_mocks(indexer)
    with patch.object(indexer, "_fanout_search_pipeline", new_callable=AsyncMock):
        doc = UnifiedDocument(
            id="t1",
            title="T",
            content="C",
            source_type="google_drive",
            url="x",
            permissions=["user:a@x.com"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            source_updated_at=datetime.now(timezone.utc),
            structured_metadata={},
        )
        await indexer.bulk_index([doc], tenant_id="tenant-abc-123")
        payload = mock_qdrant.upsert_documents.call_args[0][0][0]
        assert payload["tenant_id"] == "tenant-abc-123"


# ============================================================
# 9. LARGE CONTENT (Truncation / Embedding limits)
# ============================================================

@pytest.mark.asyncio
async def test_indexer_large_content_handling():
    """Indexer must handle oversized content gracefully (truncate or raise clear error)."""
    indexer = Indexer()
    huge_content = "A" * 10_000_000  # 10 MB
    mock_embed, mock_qdrant, mock_registry = _bind_indexer_mocks(
        indexer, embed_side_effect=ValueError("Content too large for embedding")
    )
    with patch.object(indexer, "_fanout_search_pipeline", new_callable=AsyncMock):
        doc = UnifiedDocument(
            id="big",
            title="Big Doc",
            content=huge_content,
            source_type="google_drive",
            url="x",
            permissions=["user:a@x.com"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            source_updated_at=datetime.now(timezone.utc),
            structured_metadata={},
        )
        with pytest.raises(ValueError, match="Content too large"):
            await indexer.bulk_index([doc], "tenant")
        mock_embed.embed_texts.assert_called_once()


# ============================================================
# 10. CONCURRENT OPERATIONS (Idempotency)
# ============================================================

@pytest.mark.asyncio
async def test_indexer_idempotent_upsert():
    """Indexing the same document twice should not create duplicates (Qdrant upsert)."""
    indexer = Indexer()
    mock_embed, mock_qdrant, mock_registry = _bind_indexer_mocks(indexer)
    with patch.object(indexer, "_fanout_search_pipeline", new_callable=AsyncMock):
        doc = UnifiedDocument(
            id="idempotent",
            title="Same Doc",
            content="Content",
            source_type="google_drive",
            url="x",
            permissions=["user:a@x.com"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            source_updated_at=datetime.now(timezone.utc),
            structured_metadata={},
        )
        await indexer.bulk_index([doc], "tenant")
        await indexer.bulk_index([doc], "tenant")
        assert mock_qdrant.upsert_documents.call_count == 2
        args1 = mock_qdrant.upsert_documents.call_args_list[0][0][0]
        args2 = mock_qdrant.upsert_documents.call_args_list[1][0][0]
        assert args1[0]["id"] == args2[0]["id"] == "idempotent"


# ============================================================
# 11. GMAIL EDGE CASES
# ============================================================

@pytest.mark.asyncio
async def test_gmail_transform_missing_headers(gmail_connector):
    """Gmail transform must handle messages without Subject, From, etc."""
    raw = [{
        "id": "msg_no_headers",
        "internalDate": "123",
        "payload": {"headers": []},
    }]
    docs = await gmail_connector.transform(raw)
    doc = docs[0]
    assert doc.title == ""  # or fallback
    assert doc.structured_metadata.get("from_email") == ""
    assert doc.structured_metadata.get("to_emails") == ""

@pytest.mark.asyncio
async def test_gmail_transform_no_parts(gmail_connector):
    """Gmail transform must handle messages with no body parts."""
    raw = [{
        "id": "msg_no_body",
        "internalDate": "123",
        "payload": {"headers": [{"name": "Subject", "value": "No body"}]},
    }]
    docs = await gmail_connector.transform(raw)
    assert docs[0].content == ""  # no content extracted


# ============================================================
# RUN ALL EDGE CASES
# ============================================================

def test_summary():
    print("\n✅ Edge-case test suite ready.")
    print("Run: pytest tests/test_core_edge_cases.py -v")