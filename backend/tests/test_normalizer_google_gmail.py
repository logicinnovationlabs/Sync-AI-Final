"""
Tests for Google Gmail normalizer strategy.
"""

import pytest
from app.normalizer.strategies.google_gmail import GoogleGmailNormalizer
from app.core.models import PermissionLevel


@pytest.fixture
def normalizer():
    """Create Gmail normalizer."""
    return GoogleGmailNormalizer()


@pytest.mark.asyncio
async def test_extract_text_from_snippet(normalizer):
    """Test text extraction from snippet."""
    raw = {"snippet": "This is a message snippet", "id": "msg_1", "payload": {}}
    text = await normalizer.extract_text(raw)
    
    assert text == "This is a message snippet"


@pytest.mark.asyncio
async def test_extract_text_uses_test_injection(normalizer):
    """Test text extraction uses _test_extracted_text if provided."""
    raw = {
        "snippet": "snippet",
        "id": "msg_1",
        "_test_extracted_text": "Injected test content",
        "payload": {},
    }
    text = await normalizer.extract_text(raw)
    
    assert text == "Injected test content"


def test_map_metadata_extracts_fields(normalizer):
    """Test metadata extraction."""
    raw = {
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Subject", "value": "Test Email"},
            ],
        },
        "threadId": "thread_123",
        "labelIds": ["INBOX", "UNREAD"],
        "sizeEstimate": 2048,
    }
    
    metadata = normalizer.map_metadata(raw)
    
    assert metadata["from_email"] == "sender@example.com"
    assert metadata["to_emails"] == ["recipient@example.com"]
    assert metadata["subject"] == "Test Email"
    assert metadata["thread_id"] == "thread_123"
    assert metadata["label_ids"] == ["INBOX", "UNREAD"]
    assert metadata["message_size_bytes"] == 2048


def test_extract_permission_hints_owner_only(normalizer):
    """Test that Gmail always has exactly one permission: owner."""
    raw = {
        "id": "msg_1",
        "payload": {
            "headers": [
                {"name": "Delivered-To", "value": "mailbox@example.com"},
            ],
        },
    }
    
    hints = normalizer.extract_permission_hints(raw)
    
    assert len(hints) == 1
    assert hints[0][0].email == "mailbox@example.com"
    assert hints[0][1] == PermissionLevel.OWNER


def test_extract_containers_empty(normalizer):
    """Test that Gmail has no containers."""
    raw = {"id": "msg_1", "labelIds": ["INBOX"]}
    
    containers = normalizer.extract_containers(raw)
    
    assert containers == []


def test_extract_identity_hints_owner_and_creator(normalizer):
    """Test identity hint extraction for owner and creator."""
    raw = {
        "payload": {
            "headers": [
                {"name": "Delivered-To", "value": "mailbox@example.com"},
                {"name": "From", "value": "Sender Name <sender@example.com>"},
            ],
        },
    }
    
    hints = normalizer.extract_identity_hints(raw)
    
    assert "owner" in hints
    assert hints["owner"].email == "mailbox@example.com"
    
    assert "creator" in hints
    assert hints["creator"].email == "sender@example.com"
    assert hints["creator"].name == "Sender Name"


@pytest.mark.asyncio
async def test_extract_text_falls_back_to_html_multipart(normalizer):
    """HTML-only newsletters should still yield readable plain text."""
    import base64

    html = "<p>The world claims to love authenticity.</p>"
    encoded = base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii")
    raw = {
        "snippet": "short",
        "payload": {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": encoded},
                }
            ],
        },
    }
    text = await normalizer.extract_text(raw)
    assert "authenticity" in text
    assert "<p>" not in text
