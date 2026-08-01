"""
Google Drive API client - thin wrapper around google-api-python-client.

Provides methods for:
- files.list (backfill)
- changes.list (deletion detection + incremental sync)
- files.watch (push notifications)
- permissions.list (ACL resolution)
"""

from typing import Dict, Any, List, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials


class DriveClient:
    """
    Thin wrapper around Google Drive API v3.
    
    All methods accept a token string and build the service on-demand.
    """
    
    API_SERVICE_NAME = "drive"
    API_VERSION = "v3"
    
    # Fields to fetch for files (optimization)
    FILE_FIELDS = (
        "id,name,mimeType,webViewLink,createdTime,modifiedTime,"
        "owners,permissions,size,fileExtension,parents,driveId"
    )
    
    def __init__(self):
        """Initialize Drive client."""
        pass
    
    def _build_service(self, access_token: str):
        """
        Build Drive service with access token.
        
        Args:
            access_token: Valid OAuth access token
            
        Returns:
            Drive service instance
        """
        credentials = Credentials(
            token=access_token,
            refresh_token="mock_refresh_token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="mock_client_id",
            client_secret="mock_client_secret",
        )
        return build(
            self.API_SERVICE_NAME,
            self.API_VERSION,
            credentials=credentials,
            cache_discovery=False,
        )
    
    async def list_files(
        self,
        access_token: str,
        page_size: int = 100,
        page_token: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List files (used for initial backfill).
        
        Args:
            access_token: Valid OAuth token
            page_size: Number of files per page
            page_token: Pagination token
            query: Optional query filter
            
        Returns:
            Response dict with 'files' list and 'nextPageToken'
        """
        service = self._build_service(access_token)
        
        request_params = {
            "pageSize": page_size,
            "fields": f"nextPageToken,files({self.FILE_FIELDS})",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        
        if page_token:
            request_params["pageToken"] = page_token
        
        if query:
            request_params["q"] = query
        
        try:
            response = service.files().list(**request_params).execute()
            return response
        except HttpError as e:
            raise Exception(f"Drive API error: {e}")
    
    async def list_changes(
        self,
        access_token: str,
        page_token: str,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        List changes since a given page token (incremental sync).
        
        Args:
            access_token: Valid OAuth token
            page_token: Start page token from previous sync
            page_size: Number of changes per page
            
        Returns:
            Response dict with 'changes' list, 'nextPageToken', and 'newStartPageToken'
        """
        service = self._build_service(access_token)
        
        try:
            response = service.changes().list(
                pageToken=page_token,
                pageSize=page_size,
                fields=f"nextPageToken,newStartPageToken,changes(changeType,removed,fileId,file({self.FILE_FIELDS}))",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            return response
        except HttpError as e:
            raise Exception(f"Drive changes API error: {e}")
    
    async def get_start_page_token(self, access_token: str) -> str:
        """
        Get the current start page token for changes.list.
        
        This is used to establish the baseline for incremental sync.
        
        Args:
            access_token: Valid OAuth token
            
        Returns:
            Start page token string
        """
        service = self._build_service(access_token)
        
        try:
            response = service.changes().getStartPageToken(
                supportsAllDrives=True,
            ).execute()
            return response["startPageToken"]
        except HttpError as e:
            raise Exception(f"Drive getStartPageToken API error: {e}")
    
    async def watch_changes(
        self,
        access_token: str,
        page_token: str,
        channel_id: str,
        webhook_url: str,
        channel_token: str,
        expiration: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Set up a watch channel for push notifications.
        
        Args:
            access_token: Valid OAuth token
            page_token: Start page token
            channel_id: Unique channel identifier
            webhook_url: Webhook URL to receive notifications
            channel_token: Secret token for webhook validation
            expiration: Optional expiration timestamp (milliseconds)
            
        Returns:
            Channel response with id, resourceId, expiration
        """
        service = self._build_service(access_token)
        
        body = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            "token": channel_token,
        }
        
        if expiration:
            body["expiration"] = expiration
        
        try:
            response = service.changes().watch(
                pageToken=page_token,
                body=body,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            return response
        except HttpError as e:
            raise Exception(f"Drive watch API error: {e}")
    
    async def stop_channel(
        self,
        access_token: str,
        channel_id: str,
        resource_id: str,
    ) -> None:
        """
        Stop a watch channel.
        
        Args:
            access_token: Valid OAuth token
            channel_id: Channel identifier
            resource_id: Resource identifier from watch response
        """
        service = self._build_service(access_token)
        
        body = {
            "id": channel_id,
            "resourceId": resource_id,
        }
        
        try:
            service.channels().stop(body=body).execute()
        except HttpError as e:
            # Silently ignore errors (channel may already be stopped)
            pass
    
    async def list_permissions(
        self,
        access_token: str,
        file_id: str,
    ) -> List[Dict[str, Any]]:
        """
        List permissions for a file (ACL resolution).
        
        Args:
            access_token: Valid OAuth token
            file_id: File identifier
            
        Returns:
            List of permission dicts
        """
        service = self._build_service(access_token)
        
        try:
            response = service.permissions().list(
                fileId=file_id,
                fields="permissions(type,emailAddress,role,deleted)",
                supportsAllDrives=True,
            ).execute()
            return response.get("permissions", [])
        except HttpError as e:
            # If permissions API fails, return empty (file may be deleted)
            return []
