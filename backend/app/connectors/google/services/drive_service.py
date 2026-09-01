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
import asyncio
import logging
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
from app.connectors.google.content import SKIP_MIME_TYPES, extract_drive_text

logger = logging.getLogger(__name__)


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
        connection_scope: str = "personal",
    ):
        """
        Initialize Drive connector.

        Args:
            config: Connector configuration (tenant_id, etc.)
            token_store: Token storage
            oauth_manager: Shared OAuth manager (optional, will create if not provided)
            connection_scope: Connection scope ("personal" or "organization")
        """
        super().__init__(config, token_store)
        self.tenant_id = config.get("tenant_id")
        self.oauth_manager = oauth_manager
        self.connection_scope = connection_scope
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
        from app.connectors.google.drive_credentials import get_drive_access_token

        try:
            return await get_drive_access_token(str(self.tenant_id), self.oauth_manager, self.connection_scope)
        except Exception:
            return await get_drive_access_token(str(self.tenant_id), self.oauth_manager, self.connection_scope)
    
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

        # Drive changes.list tokens are numeric. files.list pageTokens are not.
        # After backfill we store startPageToken for incremental webhooks; a later
        # backfill must not pass that token to files.list (HTTP 400 + full recrawl).
        if cursor and str(cursor).strip().isdigit():
            logger.info(
                "fetch_delta skipping files.list; cursor %r is a Drive changes token "
                "(backfill already complete)",
                cursor,
            )
            return DeltaResult(documents=[], next_cursor=None, has_more=False)
        
        # Full bootstrap crawl lists non-trashed files. Time filter is only
        # applied when the caller passes a recent `since` (incremental-style).
        query = "trashed = false"
        if since and since.year > 1971:
            # Keep a time bound for true delta-from-timestamp callers.
            from datetime import timezone as _tz
            aware = since if since.tzinfo else since.replace(tzinfo=_tz.utc)
            age_days = (datetime.utcnow().replace(tzinfo=_tz.utc) - aware).days
            if age_days < 360:
                query = f"trashed = false and modifiedTime > '{since.isoformat()}'"
        
        response = await self.drive_client.list_files(
            access_token=token,
            page_size=100,
            page_token=cursor,
            query=query,
        )
        
        files = [
            f for f in response.get("files", [])
            if f.get("mimeType") not in SKIP_MIME_TYPES
        ]
        files = await self._hydrate_files(token, files)
        
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
                file_obj = change["file"]
                if file_obj.get("mimeType") not in SKIP_MIME_TYPES:
                    files.append(file_obj)
        
        if files:
            files = await self._hydrate_files(token, files)
        
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
            
            # Content: prefer text extracted during fetch (_extracted_text).
            content = file.get("_extracted_text") or file.get("name", "")
            
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
        skipped_non_user = 0
        
        for perm in permissions:
            perm_type = perm.get("type", "")
            email = perm.get("emailAddress", "")
            deleted = perm.get("deleted", False)
            
            if deleted:
                continue
            
            if perm_type == "user" and email:
                permissions_list.append(f"user:{email}")
            elif perm_type in ("group", "anyone", "domain"):
                skipped_non_user += 1

        if skipped_non_user:
            logger.info(
                "skipped %s non-user Drive permission(s) file_id=%s",
                skipped_non_user,
                file.get("id"),
            )
        
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
        Returns a list of objects with at least {'id': <container_id or file_id>, 'type': 'container'|'document'}.
        
        This is used by the ACL revalidation Beat task.
        
        Args:
            since: Changed since this timestamp (heuristic if no pageToken stored)
            
        Returns:
            List of changed items with id and type
        """
        token = await self.get_valid_token()
        from app.services.cursor_store import cursor_store

        page_token = await cursor_store.get_cursor(str(self.tenant_id), "google_drive")
        if not page_token:
            _ = (since, token)
            return []
        delta = await self.fetch_since_page_token(page_token)
        items: List[Dict[str, Any]] = []
        for file in delta.documents or []:
            file_id = file.get("id")
            if file_id:
                items.append({"id": file_id, "type": "document"})
        for deleted_id in getattr(delta, "deleted_ids", None) or []:
            items.append({"id": deleted_id, "type": "document", "removed": True})
        return items
    
    async def _hydrate_files(
        self, access_token: str, files: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Always re-list ACLs via permissions.list, then extract text."""
        semaphore = asyncio.Semaphore(6)

        async def _one(file: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                try:
                    perms = await self.drive_client.list_permissions(
                        access_token, file.get("id", "")
                    )
                    file["permissions"] = perms or []
                except Exception:
                    logger.warning(
                        "permissions.list failed file_id=%s; compiling with empty ACL list",
                        file.get("id"),
                    )
                    file["permissions"] = []
                text = await extract_drive_text(self.drive_client, access_token, file)
                file["_extracted_text"] = text
                return file

        if not files:
            return files
        return list(await asyncio.gather(*[_one(f) for f in files]))
    
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
