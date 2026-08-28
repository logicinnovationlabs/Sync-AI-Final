"""
Integration tests for Block C pipeline.

Verifies end-to-end flow: raw -> CanonicalDocument + ACLEntry -> UnifiedDocument.
"""

import pytest
from uuid import uuid4
from datetime import datetime
from app.services.pipeline import Pipeline
from app.normalizer.registry import normalizer_registry
from app.identity.resolver import IdentityResolver
from app.identity.matchers.email_matcher import EmailMatcher
from app.identity.matchers.username_matcher import UsernameMatcher
from app.acl.compiler import ACLCompiler
from app.acl.container_service import ContainerService
from app.storage.canonical_repo import CanonicalRepo


@pytest.fixture
def pipeline():
    """Create pipeline with all dependencies."""
    canonical_repo = CanonicalRepo(use_memory=True)
    matchers = [EmailMatcher(), UsernameMatcher()]
    identity_resolver = IdentityResolver(matchers, canonical_repo)
    container_service = ContainerService(canonical_repo)
    acl_compiler = ACLCompiler(identity_resolver, container_service, canonical_repo)
    
    # Import strategies to register them
    import app.normalizer.strategies
    
    return Pipeline(
        normalizer_registry,
        identity_resolver,
        acl_compiler,
        canonical_repo,
    )


@pytest.mark.asyncio
async def test_process_raw_drive_document(pipeline):
    """Test processing a raw Drive document through the pipeline."""
    tenant_id = uuid4()
    pipeline.canonical_repo.register_login_user(tenant_id, "owner@example.com", uuid4())
    pipeline.canonical_repo.register_login_user(tenant_id, "alice@example.com", uuid4())
    
    raw = {
        "id": "file_123",
        "name": "Test Document",
        "mimeType": "text/plain",
        "fileExtension": "txt",
        "size": "1024",
        "owners": [{"emailAddress": "owner@example.com", "displayName": "Owner"}],
        "permissions": [
            {
                "type": "user",
                "emailAddress": "owner@example.com",
                "role": "owner",
                "id": "perm_1",
            },
            {
                "type": "user",
                "emailAddress": "alice@example.com",
                "role": "writer",
                "id": "perm_2",
            },
        ],
        "parents": ["folder_1"],
        "webViewLink": "https://drive.google.com/file/d/file_123",
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-02T00:00:00Z",
        "_test_extracted_text": "This is test content",
        "_test_detected_mime": "text/plain",
    }
    
    result = await pipeline.process_raw(raw, "google_drive", tenant_id)
    
    # Verify CanonicalDocument
    assert result["canonical_document"].id == "google_drive_file_123"
    assert result["canonical_document"].title == "Test Document"
    assert result["canonical_document"].content == "This is test content"
    assert result["canonical_document"].tenant_id == tenant_id
    
    # Verify ACL entries
    assert len(result["acl_entries"]) >= 2  # Owner + Alice (possibly more with expansion)
    
    # Verify UnifiedDocument has resolved permissions
    unified = result["unified_document"]
    assert unified.id == "file_123"
    assert len(unified.permissions) >= 2
    # Permissions should be "user:<uuid>" or "group:<uuid>" format, not raw emails
    assert all(p.startswith("user:") or p.startswith("group:") for p in unified.permissions)


@pytest.mark.asyncio
async def test_process_raw_gmail_message(pipeline):
    """Test processing a raw Gmail message through the pipeline."""
    tenant_id = uuid4()
    pipeline.canonical_repo.register_login_user(tenant_id, "mailbox@example.com", uuid4())
    
    raw = {
        "id": "msg_456",
        "threadId": "thread_123",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "Message snippet",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Subject", "value": "Test Email"},
                {"name": "Delivered-To", "value": "mailbox@example.com"},
            ],
        },
        "internalDate": "1704067200000",  # 2024-01-01 00:00:00 UTC in milliseconds
        "sizeEstimate": 2048,
        "_mailbox_email": "mailbox@example.com",
        "_test_extracted_text": "Email body content",
        "_test_detected_mime": "text/html",
    }
    
    result = await pipeline.process_raw(raw, "google_gmail", tenant_id)
    
    # Verify CanonicalDocument
    assert result["canonical_document"].id == "google_gmail_msg_456"
    assert result["canonical_document"].title == "Test Email"
    assert result["canonical_document"].content == "Email body content"
    assert result["canonical_document"].tenant_id == tenant_id
    
    # Verify ACL entries (Gmail has exactly one: mailbox owner)
    assert len(result["acl_entries"]) >= 1
    
    # Verify UnifiedDocument
    unified = result["unified_document"]
    assert unified.id == "msg_456"
    assert len(unified.permissions) >= 1


@pytest.mark.asyncio
async def test_process_raw_with_mime_mismatch(pipeline):
    """Test processing document with MIME mismatch."""
    tenant_id = uuid4()
    
    raw = {
        "id": "file_789",
        "name": "Suspicious File",
        "mimeType": "text/plain",
        "owners": [{"emailAddress": "owner@example.com"}],
        "permissions": [{"type": "user", "emailAddress": "owner@example.com", "role": "owner", "id": "perm_1"}],
        "parents": [],
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-01T00:00:00Z",
        "_test_extracted_text": "Content",
        "_test_detected_mime": "application/zip",
        "_test_mime_mismatch": True,
    }
    
    result = await pipeline.process_raw(raw, "google_drive", tenant_id)
    
    # Should process successfully (not crash)
    assert result["canonical_document"].id == "google_drive_file_789"
    
    # MIME mismatch should be flagged
    assert result["canonical_document"].mime_mismatch is True
    assert result["canonical_document"].mime_type == "text/plain"
    assert result["canonical_document"].detected_mime_type == "application/zip"


@pytest.mark.asyncio
async def test_process_raw_creates_resolved_identities(pipeline):
    """Test that processing creates and reuses Principal entries."""
    tenant_id = uuid4()
    alice_id = uuid4()
    pipeline.canonical_repo.register_login_user(tenant_id, "alice@example.com", alice_id)
    
    # Process first document
    raw1 = {
        "id": "file_1",
        "name": "Doc 1",
        "mimeType": "text/plain",
        "owners": [{"emailAddress": "alice@example.com"}],
        "permissions": [{"type": "user", "emailAddress": "alice@example.com", "role": "owner", "id": "perm_1"}],
        "parents": [],
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-01T00:00:00Z",
        "_test_extracted_text": "Content 1",
    }
    
    result1 = await pipeline.process_raw(raw1, "google_drive", tenant_id)
    
    # Process second document with same user
    raw2 = {
        "id": "file_2",
        "name": "Doc 2",
        "mimeType": "text/plain",
        "owners": [{"emailAddress": "alice@example.com"}],
        "permissions": [{"type": "user", "emailAddress": "alice@example.com", "role": "owner", "id": "perm_2"}],
        "parents": [],
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-01T00:00:00Z",
        "_test_extracted_text": "Content 2",
    }
    
    result2 = await pipeline.process_raw(raw2, "google_drive", tenant_id)
    
    # Should reuse same principal_id for alice@example.com
    doc1_acls = result1["acl_entries"]
    doc2_acls = result2["acl_entries"]
    
    # Find Alice's principal_id in both ACL sets
    alice_principal_id_1 = next((e.principal_id for e in doc1_acls if e.principal_id), None)
    alice_principal_id_2 = next((e.principal_id for e in doc2_acls if e.principal_id), None)
    
    assert alice_principal_id_1 is not None
    assert alice_principal_id_2 is not None
    assert alice_principal_id_1 == alice_principal_id_2  # Same principal reused
