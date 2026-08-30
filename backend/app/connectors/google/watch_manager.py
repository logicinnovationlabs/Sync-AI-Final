"""
Watch Manager - creates and renews Drive channels and Gmail Pub/Sub watches.

Manages:
- Drive files.watch channels (7-day TTL)
- Gmail users.watch Pub/Sub subscriptions (7-day TTL)

Renewal happens via Celery Beat before expiration (configurable window).
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import logging
import re

from app.connectors.google.oauth import GoogleOAuthManager
from app.connectors.google.clients.drive_client import DriveClient
from app.connectors.google.clients.gmail_client import GmailClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class WatchManager:
    """
    Manages watch channels/subscriptions for Google services.
    
    Responsibilities:
    - Register Drive watch channels
    - Register Gmail Pub/Sub watches
    - Renew expiring channels/watches
    """
    
    DEFAULT_EXPIRATION_HOURS = 168  # 7 days (Google's max)
    
    def __init__(
        self,
        oauth_manager: GoogleOAuthManager,
        cursor_store: Any = None,  # Avoid circular import
        webhook_base_url: Optional[str] = None,
        drive_client: Optional[DriveClient] = None,
        gmail_client: Optional[GmailClient] = None,
    ):
        self.oauth_manager = oauth_manager
        self.cursor_store = cursor_store
        self.webhook_base_url = webhook_base_url or settings.WEBHOOK_BASE_URL
        self.drive_client = drive_client or DriveClient()
        self.gmail_client = gmail_client or GmailClient()

    
    async def register_drive_watch(
        self,
        tenant_id: str,
        page_token: str,
        *,
        cursor_tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Register a Drive watch channel for push notifications.
        
        Should be called once after initial backfill completes.
        
        Args:
            tenant_id: Tenant identifier used for OAuth token lookup
            page_token: Start page token (from backfill's final cursor)
            cursor_tenant_id: Optional sync_cursors key (tenant:user). Defaults to tenant_id.
            
        Returns:
            Channel info dict with id, resourceId, expiration
        """
        token = await self.oauth_manager.get_valid_token(tenant_id)
        store_id = cursor_tenant_id or tenant_id
        
        # Generate unique channel ID compliant with Google regex [A-Za-z0-9\-_+/=]+
        safe_store_id = re.sub(r"[^A-Za-z0-9\-_]", "-", str(store_id))
        channel_id = f"drive-{safe_store_id}-{uuid.uuid4().hex[:8]}"[:64]
        channel_token = uuid.uuid4().hex  # Secret token for validation
        
        # Calculate expiration (Google's max is ~7 days)
        expiration_ms = int(
            (datetime.utcnow() + timedelta(hours=self.DEFAULT_EXPIRATION_HOURS)).timestamp() * 1000
        )
        
        webhook_url = f"{self.webhook_base_url}/webhooks/google/drive"
        
        try:
            response = await self.drive_client.watch_changes(
                access_token=token,
                page_token=page_token,
                channel_id=channel_id,
                webhook_url=webhook_url,
                channel_token=channel_token,
                expiration=expiration_ms,
            )
            
            # Store channel info in cursor_store
            await self.cursor_store.set_watch_info(
                tenant_id=store_id,
                source_type="google_drive",
                watch_data={
                    "channel_id": response["id"],
                    "resource_id": response["resourceId"],
                    "channel_token": channel_token,
                    "expiration": response["expiration"],
                    "page_token": page_token,
                },
            )
            
            logger.info(
                f"Registered Drive watch for tenant {tenant_id}: "
                f"channel={response['id']}, expires={response['expiration']}"
            )
            
            return response
        
        except Exception as e:
            logger.error(f"Failed to register Drive watch for tenant {tenant_id}: {e}")
            raise
    
    async def register_gmail_watch(
        self,
        tenant_id: str,
        history_id: str,
        pubsub_topic: str,
        *,
        cursor_tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Register a Gmail Pub/Sub watch for push notifications.
        
        Should be called once after initial backfill completes.
        
        Args:
            tenant_id: Tenant identifier used for OAuth token lookup
            history_id: Start history ID (from backfill's final cursor)
            pubsub_topic: Full Pub/Sub topic name (projects/{project}/topics/{topic})
            cursor_tenant_id: Optional sync_cursors key (tenant:user). Defaults to tenant_id.
            
        Returns:
            Watch info dict with historyId and expiration
        """
        token = await self.oauth_manager.get_valid_token(tenant_id)
        store_id = cursor_tenant_id or tenant_id
        
        try:
            response = await self.gmail_client.watch(
                access_token=token,
                topic_name=pubsub_topic,
            )
            
            # Calculate expiration (Gmail watch expires in 7 days)
            expiration_ms = int(response.get("expiration", 0))
            
            # Store watch info in cursor_store
            await self.cursor_store.set_watch_info(
                tenant_id=store_id,
                source_type="google_gmail",
                watch_data={
                    "history_id": response["historyId"],
                    "expiration": expiration_ms,
                    "topic_name": pubsub_topic,
                },
            )
            
            logger.info(
                f"Registered Gmail watch for tenant {tenant_id}: "
                f"historyId={response['historyId']}, expires={expiration_ms}"
            )
            
            return response
        
        except Exception as e:
            logger.error(f"Failed to register Gmail watch for tenant {tenant_id}: {e}")
            raise
    
    async def renew_expiring_watches(self) -> Dict[str, Any]:
        """
        Renew all watches expiring within the renewal window.
        
        Called by Celery Beat periodically (e.g., every 24 hours).
        
        Returns:
            Summary dict with renewal counts and errors
        """
        renewal_window_hours = getattr(
            settings, "WATCH_RENEWAL_BEFORE_EXPIRY_HOURS", 48
        )
        
        # Get all watches expiring soon
        expiring_watches = await self.cursor_store.get_expiring_watches(
            hours=renewal_window_hours
        )
        
        results = {
            "drive_renewed": 0,
            "gmail_renewed": 0,
            "errors": [],
        }
        
        for watch_info in expiring_watches:
            tenant_id = watch_info["tenant_id"]
            source_type = watch_info["source_type"]
            watch_data = watch_info["watch_data"]
            
            try:
                if source_type == "google_drive":
                    # Stop old channel
                    token = await self.oauth_manager.get_valid_token(tenant_id)
                    await self.drive_client.stop_channel(
                        access_token=token,
                        channel_id=watch_data["channel_id"],
                        resource_id=watch_data["resource_id"],
                    )
                    
                    # Register new channel with current page token
                    page_token = watch_data["page_token"]
                    await self.register_drive_watch(tenant_id, page_token)
                    
                    results["drive_renewed"] += 1
                
                elif source_type == "google_gmail":
                    # Stop old watch
                    token = await self.oauth_manager.get_valid_token(tenant_id)
                    await self.gmail_client.stop(token)
                    
                    # Register new watch with current history ID
                    history_id = watch_data["history_id"]
                    pubsub_topic = watch_data["topic_name"]
                    await self.register_gmail_watch(tenant_id, history_id, pubsub_topic)
                    
                    results["gmail_renewed"] += 1
            
            except Exception as e:
                error_msg = f"Failed to renew {source_type} watch for tenant {tenant_id}: {e}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
        
        logger.info(
            f"Watch renewal completed: "
            f"{results['drive_renewed']} Drive, "
            f"{results['gmail_renewed']} Gmail, "
            f"{len(results['errors'])} errors"
        )
        
        return results
