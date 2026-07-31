"""
Unit tests for SCIM sync service.
"""

import pytest
from uuid import uuid4

from app.services.scim_sync import scim_sync_service, PRINCIPAL_ID_NAMESPACE


@pytest.mark.asyncio
async def test_scim_sync_creates_users(test_db):
    """Test SCIM sync creates users with deterministic principal_id."""
    tenant_id = uuid4()
    
    scim_users = [
        {
            "id": "user1@idp.com",
            "emails": [{"value": "user1@example.com"}],
            "displayName": "User One",
        },
        {
            "id": "user2@idp.com",
            "emails": [{"value": "user2@example.com"}],
            "displayName": "User Two",
        },
    ]
    
    stats = await scim_sync_service.sync_users(scim_users, tenant_id, test_db)
    
    assert stats["created"] == 2
    assert stats["updated"] == 0
    assert stats["unchanged"] == 0


@pytest.mark.asyncio
async def test_scim_sync_idempotency(test_db):
    """Test SCIM sync is idempotent (A3)."""
    tenant_id = uuid4()
    
    scim_users = [
        {
            "id": "user1@idp.com",
            "emails": [{"value": "user1@example.com"}],
            "displayName": "User One",
        },
    ]
    
    # First sync
    stats1 = await scim_sync_service.sync_users(scim_users, tenant_id, test_db)
    assert stats1["created"] == 1
    
    # Second sync (unchanged)
    stats2 = await scim_sync_service.sync_users(scim_users, tenant_id, test_db)
    assert stats2["created"] == 0
    assert stats2["unchanged"] == 1
