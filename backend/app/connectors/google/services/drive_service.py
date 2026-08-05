"""
Google Drive connector service.

Implements BaseConnector for Google Drive, using the shared GoogleOAuth Manager
and DriveClient.

Methods:
- fetch_delta: Backfill path (files.list)
- fetch_deleted_ids: Deletion detection via changes.list
- fetch_since_page_token: Incremental path (used by Celery task after webhook)
- transform: Normalize Drive files to UnifiedDocument format
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import re

from app.core.base_connector import (
    BaseConnector,
    TokenStore,
    DeltaResult,
    DeletionResult,
    UnifiedDocument,
)
from app.connectors.google.oauth import GoogleOAuthManager
from app.connectors.google.clients.drive_client import DriveClient


class DriveConnector(BaseConnector):
    """
    Google Drive connector implementation.
    
    Supports both initial backfill (fetch_delta) and incremental sync
    (fetch_since_page_token) triggered by webhooks.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        token_store: TokenStore,
        oauth_manager: Optional[GoogleOAuthManager] = None,
    ):
        """
        Initialize Drive connector.
        
        Args:
            config: Connector configuration (tenant_id, etc.)
            token_store: Token storage
            oauth_manager: Shared OAuth manager (optional, will create if not provided)
        """
        super().__init__(config, token_store)
        self.tenant_id = config.get("tenant_id")
        self.oauth_manager = oauth_manager
        self.drive_client = DriveClient()
    
    def get_source_type(self) -> str:
        """Return source type identifier."""
        return "google_drive"
    
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
        Fetch files changed since timestamp (backfill path).
        
        Used only by the one-time backfill task.
        
        Args:
            since: Modified after this timestamp
            cursor: Page token from previous call
            
        Returns:
            DeltaResult with files and next cursor
        """
        token = await self.get_valid_token()
        
        # Build query to filter by modified time
        query = f"modifiedTime > '{since.isoformat()}'"
        
        response = await self.drive_client.list_files(
            access_token=token,
            page_size=100,
            page_token=cursor,
            query=query,
        )
        
        files = response.get("files", [])
        next_page_token = response.get("nextPageToken")
        
        return DeltaResult(
            documents=files,
            next_cursor=next_page_token,
            has_more=bool(next_page_token),
        )
    
    async def fetch_deleted_ids(
        self,
        since: datetime,
        cursor: Optional[str],
    ) -> DeletionResult:
        """
        Fetch deleted file IDs via changes.list (deletion baseline for backfill).
        
        Args:
            since: Deleted after this timestamp
            cursor: Start page token
            
        Returns:
            DeletionResult with deleted IDs
        """
        token = await self.get_valid_token()
        
        # If no cursor, get current start page token
        if not cursor:
            cursor = await self.drive_client.get_start_page_token(token)
        
        response = await self.drive_client.list_changes(
            access_token=token,
            page_token=cursor,
            page_size=100,
        )
        
        # Extract deleted file IDs
        deleted_ids = []
        changes = response.get("changes", [])
        
        for change in changes:
            if change.get("removed") or change.get("changeType") == "file":
                file_id = change.get("fileId")
                if file_id and change.get("removed"):
                    deleted_ids.append(file_id)
        
        next_page_token = response.get("nextPageToken") or response.get("newStartPageToken")
        
        return DeletionResult(
            deleted_ids=deleted_ids,
            next_cursor=next_page_token,
            has_more=bool(response.get("nextPageToken")),
        )
    
    async def fetch_since_page_token(self, page_token: str) -> DeltaResult:
        """
        Fetch changes since a stored page token (incremental path).
        
        This is NOT part of BaseConnector - it's used by the Celery task
        triggered by webhooks.
        
        Args:
            page_token: Start page token from cursor_store
            
        Returns:
            DeltaResult with changed/added files and new cursor
        """
        token = await self.get_valid_token()
        
        response = await self.drive_client.list_changes(
            access_token=token,
            page_token=page_token,
            page_size=100,
        )
        
        # Extract files from changes (filter out removed items)
        files = []
        deleted_ids = []
        changes = response.get("changes", [])
        
        for change in changes:
            if change.get("removed"):
                deleted_ids.append(change.get("fileId"))
            elif change.get("file"):
                files.append(change["file"])
        
        next_page_token = response.get("newStartPageToken") or response.get("nextPageToken")
        
        # Store deleted IDs in the documents metadata for processing
        result = DeltaResult(
            documents=files,
            next_cursor=next_page_token,
            has_more=bool(response.get("nextPageToken")),
        )
        
        # Attach deleted IDs for the Celery task to handle
        if deleted_ids:
            result.deleted_ids = deleted_ids
        
        return result
    
    async def transform(self, raw_documents: List[Dict[str, Any]]) -> List[UnifiedDocument]:
        """
        Transform Drive files to UnifiedDocument format.
        
        Args:
            raw_documents: Raw file dicts from Drive API
            
        Returns:
            List of UnifiedDocument instances
        """
        unified_docs = []
        
        for file in raw_documents:
            file_id = file.get("id")
            if not file_id:
                continue
            
            # Resolve permissions to user:/group: format
            permissions = await self._resolve_permissions(file)
            
            # Extract metadata
            mime_type = file.get("mimeType", "")
            file_extension = file.get("fileExtension", "")
            size_bytes = file.get("size", 0)
            
            # Owner email
            owners = file.get("owners", [])
            owner_email = owners[0].get("emailAddress", "") if owners else ""
            
            # Metadata allowlist (from manifest.yaml)
            structured_metadata = {
                "mime_type": mime_type,
                "file_extension": file_extension,
                "owner_email": owner_email,
                "shared_drive_id": file.get("driveId", ""),
                "parent_folder_id": file.get("parents", [""])[0],
                "web_view_link": file.get("webViewLink", ""),
                "size_bytes": size_bytes,
            }
            
            # Content: for Google Docs, we can't get content via API without export
            # For now, just use file name as content (real impl would export as text)
            content = file.get("name", "")
            
            unified_doc = UnifiedDocument(
                id=file_id,
                title=file.get("name", "Untitled"),
                content=content,
                source_type=self.get_source_type(),
                url=file.get("webViewLink", f"https://drive.google.com/file/d/{file_id}"),
                permissions=permissions,
                created_at=self._parse_timestamp(file.get("createdTime")),
                updated_at=datetime.utcnow(),
                source_updated_at=self._parse_timestamp(file.get("modifiedTime")),
                structured_metadata=structured_metadata,
            )
            
            unified_docs.append(unified_doc)
        
        return unified_docs
    
    async def _resolve_permissions(self, file: Dict[str, Any]) -> List[str]:
        """
        Resolve file permissions to user:/group: format.
        
        Args:
            file: File dict with permissions
            
        Returns:
            List of permission strings
        """
        permissions_list = []
        permissions = file.get("permissions", [])
        
        for perm in permissions:
            perm_type = perm.get("type", "")
            email = perm.get("emailAddress", "")
            deleted = perm.get("deleted", False)
            
            if deleted:
                continue
            
            if perm_type == "user" and email:
                permissions_list.append(f"user:{email}")
            elif perm_type == "group" and email:
                permissions_list.append(f"group:{email}")
            elif perm_type == "anyone":
                # Public file - use special permission
                permissions_list.append("user:*")
        
        # If no permissions found, default to owner
        if not permissions_list:
            owners = file.get("owners", [])
            if owners:
                owner_email = owners[0].get("emailAddress", "")
                if owner_email:
                    permissions_list.append(f"user:{owner_email}")
        
        return permissions_list
    
    async def fetch_permission_changes(self, since: datetime) -> List[Dict[str, Any]]:
        """
        Fetch containers/documents whose permissions changed since a given timestamp.
        
        Uses Drive's changes.list with a stored pageToken for ACL revalidation.
        Returns a list of objects with at least
        {'id': <container_id or file_id>, 'type': 'container'|'document'}.
        
        Stub for Block C ACL revalidation Beat task — returns [] until wired.
        """
        token = await self.get_valid_token()
        _ = (since, token)
        return []
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> datetime:
        """
        Parse Google's RFC3339 timestamp.
        
        Args:
            timestamp_str: Timestamp string or None
            
        Returns:
            datetime object
        """
        if not timestamp_str:
            return datetime.utcnow()
        
        # Remove timezone suffix for parsing
        clean_ts = re.sub(r'[+-]\d{2}:\d{2}$|Z$', '', timestamp_str)
        
        try:
            return datetime.fromisoformat(clean_ts)
        except ValueError:
            return datetime.utcnow()
