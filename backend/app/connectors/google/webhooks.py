"""
Google push notification webhook receivers.

FastAPI routes that:
1. Validate incoming notifications (Drive channel token / Gmail Pub/Sub auth)
2. Enqueue Celery tasks for incremental processing
3. Return immediately (no fetching/indexing in the webhook handler)

Endpoints:
- POST /webhooks/google/drive - Drive push notifications
- POST /webhooks/google/gmail - Gmail Pub/Sub push notifications
"""

from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional
import logging

from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/google", tags=["webhooks"])


@router.post("/drive")
async def drive_webhook(
    request: Request,
    x_goog_channel_id: Optional[str] = Header(None),
    x_goog_channel_token: Optional[str] = Header(None),
    x_goog_resource_id: Optional[str] = Header(None),
    x_goog_resource_state: Optional[str] = Header(None),
):
    """
    Receive Drive push notifications.
    
    Validates the channel token and enqueues a Celery task for incremental sync.
    
    Headers:
        X-Goog-Channel-Id: Channel identifier
        X-Goog-Channel-Token: Secret token for validation
        X-Goog-Resource-Id: Resource identifier
        X-Goog-Resource-State: State ('sync' | 'exists' | 'not_exists' | 'update')
    
    Returns:
        200 OK if accepted
        403 Forbidden if validation fails
    """
    from app.services.cursor_store import cursor_store
    from app.workers.tasks import process_drive_notification
    
    # Ignore 'sync' state (initial handshake)
    if x_goog_resource_state == "sync":
        return {"status": "sync_acknowledged"}
    
    if not x_goog_channel_id or not x_goog_channel_token or not x_goog_resource_id:
        logger.warning("Drive webhook missing required headers")
        raise HTTPException(status_code=400, detail="Missing required headers")
    
    # Validate channel token
    try:
        watch_info = await cursor_store.get_watch_by_channel(
            channel_id=x_goog_channel_id,
            resource_id=x_goog_resource_id,
        )
        
        if not watch_info:
            logger.warning(f"Unknown Drive channel: {x_goog_channel_id}")
            raise HTTPException(status_code=403, detail="Invalid channel")
        
        stored_token = watch_info["watch_data"].get("channel_token")
        if stored_token != x_goog_channel_token:
            logger.warning(
                f"Invalid channel token for channel {x_goog_channel_id}: "
                f"expected {stored_token}, got {x_goog_channel_token}"
            )
            raise HTTPException(status_code=403, detail="Invalid channel token")
        
        tenant_id = watch_info["tenant_id"]
        
        # Enqueue Celery task with trace context propagation (§2.4)
        _otel_headers = {}
        TraceContextTextMapPropagator().inject(_otel_headers)
        process_drive_notification.apply_async(
            args=[tenant_id], headers=_otel_headers
        )
        
        logger.info(
            f"Drive notification accepted for tenant {tenant_id}, "
            f"channel {x_goog_channel_id}, state {x_goog_resource_state}"
        )
        
        return {"status": "accepted"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Drive webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/gmail")
async def gmail_webhook(request: Request):
    """
    Receive Gmail Pub/Sub push notifications.
    
    Validates the Pub/Sub message and enqueues a Celery task for incremental sync.
    
    Body (JSON):
        {
          "message": {
            "data": "<base64-encoded-data>",
            "messageId": "...",
            "publishTime": "..."
          },
          "subscription": "..."
        }
    
    Returns:
        200 OK if accepted
        403 Forbidden if validation fails
    """
    from app.services.cursor_store import cursor_store
    from app.workers.tasks import process_gmail_notification
    from app.core.config import settings
    import base64
    import json
    
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    # Extract message data
    message = body.get("message", {})
    data_b64 = message.get("data", "")
    
    if not data_b64:
        logger.warning("Gmail webhook missing message data")
        raise HTTPException(status_code=400, detail="Missing message data")
    
    # Decode data
    try:
        data_json = base64.b64decode(data_b64).decode("utf-8")
        data = json.loads(data_json)
    except Exception as e:
        logger.error(f"Failed to decode Gmail Pub/Sub data: {e}")
        raise HTTPException(status_code=400, detail="Invalid message data")
    
    # Extract email address from data
    email_address = data.get("emailAddress")
    history_id = data.get("historyId")
    
    if not email_address:
        logger.warning("Gmail webhook missing emailAddress")
        raise HTTPException(status_code=400, detail="Missing emailAddress")
    
    # Optional: Validate verification token
    # (If configured, check a custom header or data field)
    verification_token = getattr(settings, "GOOGLE_PUBSUB_VERIFICATION_TOKEN", None)
    if verification_token:
        # Check if token matches (could be in headers or data)
        provided_token = request.headers.get("X-Verification-Token") or data.get("token")
        if provided_token != verification_token:
            logger.warning(f"Invalid Pub/Sub verification token")
            raise HTTPException(status_code=403, detail="Invalid verification token")
    
    # Resolve tenant from email address
    try:
        watch_info = await cursor_store.get_watch_by_email(
            email_address=email_address,
            source_type="google_gmail",
        )
        
        if not watch_info:
            logger.warning(f"Unknown Gmail watch for email: {email_address}")
            raise HTTPException(status_code=403, detail="Unknown watch")
        
        tenant_id = watch_info["tenant_id"]
        
        # Update stored history ID if provided
        if history_id:
            await cursor_store.update_cursor(
                tenant_id=tenant_id,
                source_type="google_gmail",
                cursor=history_id,
            )
        
        # Enqueue Celery task with trace context propagation (§2.4)
        _otel_headers = {}
        TraceContextTextMapPropagator().inject(_otel_headers)
        process_gmail_notification.apply_async(
            args=[tenant_id], headers=_otel_headers
        )
        
        logger.info(
            f"Gmail notification accepted for tenant {tenant_id}, "
            f"email {email_address}, historyId {history_id}"
        )
        
        return {"status": "accepted"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Gmail webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
