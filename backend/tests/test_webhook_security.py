"""
Webhook security tests - verify channel token validation is enforced.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_drive_webhook_rejects_invalid_channel_token():
    """
    Verify Drive webhook rejects requests with invalid channel tokens.
    Channel token validation must happen BEFORE process_drive_notification is enqueued.
    """
    from app.main import app
    from app.services.cursor_store import cursor_store
    
    client = TestClient(app)
    
    # Mock cursor_store to return a valid watch with a specific token
    mock_watch_info = {
        "tenant_id": "test-tenant-123",
        "watch_data": {
            "channel_token": "correct-secret-token"
        }
    }
    
    with patch.object(cursor_store, "get_watch_by_channel", new_callable=AsyncMock) as mock_get_watch:
        mock_get_watch.return_value = mock_watch_info
        
        # Mock process_drive_notification to track if it was called
        with patch("app.workers.tasks.process_drive_notification") as mock_task:
            # Send request with WRONG channel token
            response = client.post(
                "/webhooks/google/drive",
                headers={
                    "X-Goog-Channel-Id": "test-channel-123",
                    "X-Goog-Channel-Token": "wrong-token",  # Invalid token
                    "X-Goog-Resource-Id": "resource-123",
                    "X-Goog-Resource-State": "exists",
                }
            )
            
            # Assert: 403 Forbidden
            assert response.status_code == 403
            assert "Invalid channel token" in response.json()["detail"]
            
            # Assert: process_drive_notification was NEVER called
            mock_task.apply_async.assert_not_called()


@pytest.mark.asyncio
async def test_drive_webhook_rejects_missing_channel_token():
    """
    Verify Drive webhook rejects requests with missing channel token.
    """
    from app.main import app
    from app.services.cursor_store import cursor_store
    
    client = TestClient(app)
    
    with patch.object(cursor_store, "get_watch_by_channel", new_callable=AsyncMock):
        with patch("app.workers.tasks.process_drive_notification") as mock_task:
            # Send request without channel token header
            response = client.post(
                "/webhooks/google/drive",
                headers={
                    "X-Goog-Channel-Id": "test-channel-123",
                    # X-Goog-Channel-Token missing
                    "X-Goog-Resource-Id": "resource-123",
                    "X-Goog-Resource-State": "exists",
                }
            )
            
            # Assert: 400 Bad Request
            assert response.status_code == 400
            assert "Missing required headers" in response.json()["detail"]
            
            # Assert: process_drive_notification was NEVER called
            mock_task.apply_async.assert_not_called()


@pytest.mark.asyncio
async def test_drive_webhook_accepts_valid_channel_token():
    """
    Verify Drive webhook accepts requests with valid channel token and enqueues task.
    """
    from app.main import app
    from app.services.cursor_store import cursor_store
    
    client = TestClient(app)
    
    mock_watch_info = {
        "tenant_id": "test-tenant-123",
        "watch_data": {
            "channel_token": "correct-secret-token"
        }
    }
    
    with patch.object(cursor_store, "get_watch_by_channel", new_callable=AsyncMock) as mock_get_watch:
        mock_get_watch.return_value = mock_watch_info
        
        with patch("app.workers.tasks.process_drive_notification") as mock_task:
            mock_task.apply_async.return_value = None
            
            # Send request with CORRECT channel token
            response = client.post(
                "/webhooks/google/drive",
                headers={
                    "X-Goog-Channel-Id": "test-channel-123",
                    "X-Goog-Channel-Token": "correct-secret-token",  # Valid token
                    "X-Goog-Resource-Id": "resource-123",
                    "X-Goog-Resource-State": "exists",
                }
            )
            
            # Assert: 200 OK
            assert response.status_code == 200
            assert response.json()["status"] == "accepted"
            
            # Assert: process_drive_notification WAS called
            mock_task.apply_async.assert_called_once()
