"""
Tests for Google Drive normalizer strategy.
"""

import pytest
from app.normalizer.strategies.google_drive import GoogleDriveNormalizer
from app.core.models import PermissionLevel


@pytest.fixture
def normalizer():
    """Create Drive normalizer."""
    return GoogleDriveNormalizer()


@pytest.mark.asyncio
async def test_extract_text_returns_name_placeholder(normalizer):
    """Test text extraction returns file name as placeholder."""
    raw = {"name": "Test Document", "id": "file_1"}
    text = await normalizer.extract_text(raw)
    
    assert text == "Test Document"


@pytest.mark.asyncio
async def test_extract_text_uses_test_injection(normalizer):
    """Test text extraction uses _test_extracted_text if provided."""
    raw = {
        "name": "Test Document",
        "id": "file_1",
        "_test_extracted_text": "Injected test content",
    }
    text = await normalizer.extract_text(raw)
    
    assert text == "Injected test content"


def test_map_metadata_extracts_fields(normalizer):
    """Test metadata extraction."""
    raw = {
        "mimeType": "application/pdf",
        "fileExtension": "pdf",
        "size": "1024",
        "owners": [{"emailAddress": "owner@example.com"}],
        "driveId": "drive_123",
        "parents": ["folder_1"],
        "webViewLink": "https://drive.google.com/file/d/file_1",
    }
    
    metadata = normalizer.map_metadata(raw)
    
    assert metadata["mime_type"] == "application/pdf"
    assert metadata["file_extension"] == "pdf"
    assert metadata["size_bytes"] == 1024
    assert metadata["owner_email"] == "owner@example.com"
    assert metadata["shared_drive_id"] == "drive_123"
    assert metadata["parent_folder_id"] == "folder_1"


def test_extract_permission_hints_user_permissions(normalizer):
    """Test extraction of user permissions."""
    raw = {
        "id": "file_1",
        "permissions": [
            {
                "type": "user",
                "emailAddress": "alice@example.com",
                "role": "owner",
                "id": "perm_1",
            },
            {
                "type": "user",
                "emailAddress": "bob@example.com",
                "role": "writer",
                "id": "perm_2",
            },
        ],
    }
    
    hints = normalizer.extract_permission_hints(raw)
    
    assert len(hints) == 2
    assert hints[0][0].email == "alice@example.com"
    assert hints[0][1] == PermissionLevel.OWNER
    assert hints[1][0].email == "bob@example.com"
    assert hints[1][1] == PermissionLevel.WRITE


def test_extract_permission_hints_group_permissions(normalizer):
    """Test extraction of group permissions."""
    raw = {
        "id": "file_1",
        "permissions": [
            {
                "type": "group",
                "emailAddress": "eng@example.com",
                "role": "reader",
                "id": "perm_1",
            },
        ],
    }
    
    hints = normalizer.extract_permission_hints(raw)
    
    assert len(hints) == 1
    assert hints[0][0].email == "eng@example.com"
    assert hints[0][1] == PermissionLevel.READ


def test_extract_containers(normalizer):
    """Test container extraction."""
    raw = {"parents": ["folder_1", "folder_2"]}
    
    containers = normalizer.extract_containers(raw)
    
    assert containers == ["folder_1", "folder_2"]


def test_extract_identity_hints_owner(normalizer):
    """Test identity hint extraction for owner."""
    raw = {
        "owners": [
            {
                "emailAddress": "owner@example.com",
                "displayName": "Owner Name",
                "permissionId": "perm_123",
            }
        ],
    }
    
    hints = normalizer.extract_identity_hints(raw)
    
    assert "owner" in hints
    assert hints["owner"].email == "owner@example.com"
    assert hints["owner"].name == "Owner Name"
    
    # Drive doesn't distinguish creator, so it should use owner
    assert "creator" in hints
    assert hints["creator"].email == hints["owner"].email
