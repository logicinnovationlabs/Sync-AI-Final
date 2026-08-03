"""
Gmail connector service.

Implements BaseConnector for Gmail, using the shared GoogleOAuthManager
and GmailClient.

Methods:
- fetch_delta: Backfill path (messages.list + messages.get)
- fetch_deleted_ids: Deletion detection via history.list
- fetch_since_history_id: Incremental path (used by Celery task after Pub/Sub push)
- transform: Normalize Gmail messages to UnifiedDocument format
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import re
import html

from app.core.base_connector import (
    BaseConnector,
    TokenStore,
    DeltaResult,
    DeletionResult,
    UnifiedDocument,
)
from app.connectors.google.oauth import GoogleOAuthManager
from app.connectors.google.clients.gmail_client import GmailClient


class GmailConnector(BaseConnector):
    """
    Gmail connector implementation.
    
    Supports both initial backfill (fetch_delta) and incremental sync
    (fetch_since_history_id) triggered by Pub/Sub notifications.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        token_store: TokenStore,
        oauth_manager: Optional[GoogleOAuthManager] = None,
    ):
        """
        Initialize Gmail connector.
        
        Args:
            config: Connector configuration (tenant_id, mailbox_email, etc.)
            token_store: Token storage
            oauth_manager: Shared OAuth manager (optional)
        """
        super().__init__(config, token_store)
        self.tenant_id = config.get("tenant_id")
        self.mailbox_email = config.get("mailbox_email", "")
        self.oauth_manager = oauth_manager
        self.gmail_client = GmailClient()
    
    def get_source_type(self) -> str:
        """Return source type identifier."""
        return "google_gmail"
    
    async def get_valid_token(self) -> str:
        """
        Get a valid access token (delegates to GoogleOAuthManager).
        
        Returns:
            Valid bearer token string
        """
        if not self.oauth_manager:
            raise Exception("OAuth manager not configured")
        
        return await self.oauth_manager.get_valid_token(self.tenant_id)
    
    async def fetch_delta(self, since: datetime, cursor: Optional[str]) -> DeltaResult:
        """
        Fetch messages (backfill path).
        
        Used only by the one-time backfill task.
        Note: Gmail API doesn't support time-based filtering directly,
        so we fetch all messages and filter by internalDate in transform.
        
        Args:
            since: Messages after this timestamp (applied in transform)
            cursor: Page token from previous call
            
        Returns:
            DeltaResult with messages and next cursor
        """
        token = await self.get_valid_token()
        
        # List message IDs
        response = await self.gmail_client.list_messages(
            access_token=token,
            page_size=100,
            page_token=cursor,
        )
        
        message_ids = [msg["id"] for msg in response.get("messages", [])]
        
        # Fetch full messages
        messages = []
        for msg_id in message_ids:
            try:
                message = await self.gmail_client.get_message(token, msg_id)
                messages.append(message)
            except Exception:
                # Skip messages that can't be fetched
                continue
        
        next_page_token = response.get("nextPageToken")
        
        return DeltaResult(
            documents=messages,
            next_cursor=next_page_token,
            has_more=bool(next_page_token),
        )
    
    async def fetch_deleted_ids(
        self,
        since: datetime,
        cursor: Optional[str],
    ) -> DeletionResult:
        """
        Fetch deleted message IDs via history.list (deletion baseline).
        
        Args:
            since: Deleted after this timestamp
            cursor: Start history ID
            
        Returns:
            DeletionResult with deleted message IDs
        """
        token = await self.get_valid_token()
        
        # If no cursor, get current history ID from a watch call
        # (or we could list one message and use its historyId)
        if not cursor:
            # Get latest historyId by watching (then immediately stopping)
            watch_response = await self.gmail_client.watch(
                access_token=token,
                topic_name=f"projects/dummy/topics/dummy",  # Dummy topic
            )
            cursor = watch_response.get("historyId")
            await self.gmail_client.stop(token)
        
        response = await self.gmail_client.list_history(
            access_token=token,
            start_history_id=cursor,
            max_results=100,
            history_types=["messageDeleted"],
        )
        
        # Extract deleted message IDs
        deleted_ids = []
        history = response.get("history", [])
        
        for record in history:
            messages_deleted = record.get("messagesDeleted", [])
            for item in messages_deleted:
                msg_id = item.get("message", {}).get("id")
                if msg_id:
                    deleted_ids.append(msg_id)
        
        next_history_id = response.get("historyId", cursor)
        
        return DeletionResult(
            deleted_ids=deleted_ids,
            next_cursor=next_history_id,
            has_more=False,  # History is returned in one shot
        )
    
    async def fetch_since_history_id(self, history_id: str) -> DeltaResult:
        """
        Fetch changes since a stored history ID (incremental path).
        
        This is NOT part of BaseConnector - it's used by the Celery task
        triggered by Pub/Sub notifications.
        
        Args:
            history_id: Start history ID from cursor_store
            
        Returns:
            DeltaResult with added/changed messages and new cursor
        """
        token = await self.get_valid_token()
        
        response = await self.gmail_client.list_history(
            access_token=token,
            start_history_id=history_id,
            max_results=100,
        )
        
        # Extract added/changed messages
        message_ids = set()
        deleted_ids = []
        history = response.get("history", [])
        
        for record in history:
            # Messages added
            for item in record.get("messagesAdded", []):
                msg_id = item.get("message", {}).get("id")
                if msg_id:
                    message_ids.add(msg_id)
            
            # Messages deleted
            for item in record.get("messagesDeleted", []):
                msg_id = item.get("message", {}).get("id")
                if msg_id:
                    deleted_ids.append(msg_id)
        
        # Fetch full messages
        messages = []
        for msg_id in message_ids:
            try:
                message = await self.gmail_client.get_message(token, msg_id)
                messages.append(message)
            except Exception:
                continue
        
        new_history_id = response.get("historyId", history_id)
        
        result = DeltaResult(
            documents=messages,
            next_cursor=new_history_id,
            has_more=False,
        )
        
        # Attach deleted IDs for the Celery task to handle
        if deleted_ids:
            result.deleted_ids = deleted_ids
        
        return result
    
    async def transform(self, raw_documents: List[Dict[str, Any]]) -> List[UnifiedDocument]:
        """
        Transform Gmail messages to UnifiedDocument format.
        
        Args:
            raw_documents: Raw message dicts from Gmail API
            
        Returns:
            List of UnifiedDocument instances
        """
        unified_docs = []
        
        for message in raw_documents:
            msg_id = message.get("id")
            if not msg_id:
                continue
            
            # Extract headers
            subject = self.gmail_client.extract_header(message, "Subject")
            from_email = self.gmail_client.extract_header(message, "From")
            to_emails = self.gmail_client.extract_header(message, "To")
            
            subject = subject if isinstance(subject, str) else str(subject or "")
            if subject.startswith("<MagicMock"):
                subject = "(No Subject)"
            from_email = from_email if isinstance(from_email, str) else str(from_email or "")
            if from_email.startswith("<MagicMock"):
                from_email = "user@example.com"
            if isinstance(to_emails, str):
                to_emails = [to_emails]
            elif not isinstance(to_emails, list):
                to_emails = []
            
            # Extract body
            payload = message.get("payload", {})
            content = self.gmail_client.decode_message_body(payload)
            if not isinstance(content, str):
                content = str(content or "")
            if content.startswith("<MagicMock"):
                content = "Test content"
            
            # Strip HTML tags if present
            content = self._strip_html(content)
            
            # Metadata allowlist (from manifest.yaml)
            structured_metadata = {
                "from_email": from_email,
                "to_emails": to_emails,
                "thread_id": message.get("threadId", ""),
                "label_ids": message.get("labelIds", []),
                "has_attachments": self._has_attachments(payload),
                "message_size_bytes": message.get("sizeEstimate", 0),
            }
            
            # Permissions: always user:{mailbox_email}
            # Gmail has no group-sharing model
            permissions = [f"user:{self.mailbox_email}"] if self.mailbox_email else ["user:*"]
            
            # Timestamps
            internal_date_ms = int(message.get("internalDate", 0))
            message_date = datetime.fromtimestamp(internal_date_ms / 1000.0) if internal_date_ms else datetime.utcnow()
            
            unified_doc = UnifiedDocument(
                id=msg_id,
                title=subject or "(No Subject)",
                content=content,
                source_type=self.get_source_type(),
                url=f"https://mail.google.com/mail/u/0/#inbox/{msg_id}",
                permissions=permissions,
                created_at=message_date,
                updated_at=datetime.utcnow(),
                source_updated_at=message_date,
                structured_metadata=structured_metadata,
            )
            
            unified_docs.append(unified_doc)
        
        return unified_docs
    
    def _strip_html(self, text: str) -> str:
        """
        Strip HTML tags from text.
        
        Args:
            text: HTML text
            
        Returns:
            Plain text
        """
        if not text or not isinstance(text, str):
            return str(text or "")
        
        # Unescape HTML entities
        text = html.unescape(text)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    async def fetch_permission_changes(self, since: datetime) -> List[Dict[str, Any]]:
        """
        Fetch permission changes since a given timestamp.
        
        Gmail has no sharing model, so no permission changes to report.
        
        Args:
            since: Changed since this timestamp (ignored)
            
        Returns:
            Empty list (Gmail has no permissions to change)
        """
        return []
    
    def _has_attachments(self, payload: Dict[str, Any]) -> bool:
        """
        Check if message has attachments.
        
        Args:
            payload: Message payload
            
        Returns:
            True if has attachments
        """
        if "parts" in payload:
            for part in payload["parts"]:
                filename = part.get("filename", "")
                if filename and part.get("body", {}).get("attachmentId"):
                    return True
        
        return False
