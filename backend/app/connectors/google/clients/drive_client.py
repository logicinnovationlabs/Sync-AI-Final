"""
Google Drive API client - high-performance async client using httpx.

Provides methods for:
- files.list (backfill)
- changes.list (deletion detection + incremental sync)
- changes.getStartPageToken
- changes.watch (push notifications)
- channels.stop
- permissions.list (ACL resolution)
- files.export (Google-native Docs/Sheets/Slides export)
- files.get_media (binary download)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DRIVE_ROOT = "https://www.googleapis.com/drive/v3"


class DriveClient:
    """
    Async client for Google Drive API v3 using httpx with connection pooling.
    """

    API_SERVICE_NAME = "drive"
    API_VERSION = "v3"

    # Fields to fetch for files (optimization)
    FILE_FIELDS = (
        "id,name,mimeType,webViewLink,createdTime,modifiedTime,"
        "owners,permissions,size,fileExtension,parents,driveId"
    )

    def __init__(self, timeout: float = 60.0):
        """Initialize Drive client."""
        self.timeout = timeout

    def _headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

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
        params: Dict[str, Any] = {
            "pageSize": page_size,
            "fields": f"nextPageToken,files({self.FILE_FIELDS})",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        if query:
            params["q"] = query

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{DRIVE_ROOT}/files",
                    params=params,
                    headers=self._headers(access_token),
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"Drive API error: {e}") from e
        except Exception as e:
            raise Exception(f"Drive API error: {e}") from e

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
        params: Dict[str, Any] = {
            "pageToken": page_token,
            "pageSize": page_size,
            "fields": f"nextPageToken,newStartPageToken,changes(changeType,removed,fileId,file({self.FILE_FIELDS}))",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{DRIVE_ROOT}/changes",
                    params=params,
                    headers=self._headers(access_token),
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"Drive changes API error: {e}") from e
        except Exception as e:
            raise Exception(f"Drive changes API error: {e}") from e

    async def get_start_page_token(self, access_token: str) -> str:
        """
        Get the current start page token for changes.list.

        Args:
            access_token: Valid OAuth token

        Returns:
            Start page token string
        """
        params = {"supportsAllDrives": "true"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{DRIVE_ROOT}/changes/startPageToken",
                    params=params,
                    headers=self._headers(access_token),
                )
                resp.raise_for_status()
                data = resp.json()
                return data["startPageToken"]
        except httpx.HTTPStatusError as e:
            raise Exception(f"Drive getStartPageToken API error: {e}") from e
        except Exception as e:
            raise Exception(f"Drive getStartPageToken API error: {e}") from e

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
        params = {
            "pageToken": page_token,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }

        body: Dict[str, Any] = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            "token": channel_token,
        }
        if expiration:
            body["expiration"] = expiration

        headers = self._headers(access_token)
        headers["Content-Type"] = "application/json"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{DRIVE_ROOT}/changes/watch",
                    params=params,
                    json=body,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"Drive watch API error: {e}") from e
        except Exception as e:
            raise Exception(f"Drive watch API error: {e}") from e

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
        body = {
            "id": channel_id,
            "resourceId": resource_id,
        }
        headers = self._headers(access_token)
        headers["Content-Type"] = "application/json"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                await client.post(
                    f"{DRIVE_ROOT}/channels/stop",
                    json=body,
                    headers=headers,
                )
        except Exception as e:
            # Silently ignore errors (channel may already be stopped)
            logger.debug(f"Drive stop channel failed (ignored): {e}")

    async def export_file(
        self,
        access_token: str,
        file_id: str,
        mime_type: str = "text/plain",
    ) -> bytes:
        """Export a Google-native file (Docs/Sheets/Slides) as the given MIME type."""
        params = {"mimeType": mime_type}
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(
                    f"{DRIVE_ROOT}/files/{file_id}/export",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.content
        except httpx.HTTPStatusError as e:
            raise Exception(f"Drive export API error: {e}") from e
        except Exception as e:
            raise Exception(f"Drive export API error: {e}") from e

    async def download_file(self, access_token: str, file_id: str) -> bytes:
        """Download binary file bytes via files.get?alt=media."""
        params = {
            "alt": "media",
            "supportsAllDrives": "true",
        }
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(
                    f"{DRIVE_ROOT}/files/{file_id}",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.content
        except httpx.HTTPStatusError as e:
            raise Exception(f"Drive download API error: {e}") from e
        except Exception as e:
            raise Exception(f"Drive download API error: {e}") from e

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
        params = {
            "fields": "permissions(id,type,role,emailAddress,domain,deleted)",
            "supportsAllDrives": "true",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{DRIVE_ROOT}/files/{file_id}/permissions",
                    params=params,
                    headers=self._headers(access_token),
                )
                if resp.status_code == 404:
                    return []
                resp.raise_for_status()
                data = resp.json()
                return data.get("permissions", [])
        except Exception as e:
            # If permissions API fails, return empty (file may be deleted or no access)
            logger.debug(f"Drive list permissions failed for {file_id}: {e}")
            return []
