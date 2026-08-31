"""
Gmail API client - high-performance async client using httpx.

Provides methods for:
- messages.list (backfill)
- messages.get (fetch full message)
- history.list (incremental sync + deletion detection)
- users.watch (Pub/Sub push notifications)
- users.stop
- users.getProfile
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

GMAIL_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailClient:
    """
    Async client for Gmail API v1 using httpx with connection pooling.
    """

    API_SERVICE_NAME = "gmail"
    API_VERSION = "v1"
    USER_ID = "me"

    def __init__(self, timeout: float = 30.0):
        """Initialize Gmail client."""
        self.timeout = timeout

    def _headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    async def list_messages(
        self,
        access_token: str,
        page_size: int = 100,
        page_token: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List messages (used for initial backfill).

        Args:
            access_token: Valid OAuth token
            page_size: Number of messages per page
            page_token: Pagination token
            query: Optional Gmail search query

        Returns:
            Response dict with 'messages' list and 'nextPageToken'
        """
        params: Dict[str, Any] = {
            "maxResults": page_size,
        }
        if page_token:
            params["pageToken"] = page_token
        if query:
            params["q"] = query

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{GMAIL_ROOT}/messages",
                    params=params,
                    headers=self._headers(access_token),
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"Gmail API error: {e}") from e
        except Exception as e:
            raise Exception(f"Gmail API error: {e}") from e

    async def get_message(
        self,
        access_token: str,
        message_id: str,
        format: str = "full",
    ) -> Dict[str, Any]:
        """
        Get a single message by ID.

        Args:
            access_token: Valid OAuth token
            message_id: Message identifier
            format: Message format ('full', 'metadata', 'minimal', 'raw')

        Returns:
            Message dict with headers, payload, etc.
        """
        params = {"format": format}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{GMAIL_ROOT}/messages/{message_id}",
                    params=params,
                    headers=self._headers(access_token),
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"Gmail get message API error: {e}") from e
        except Exception as e:
            raise Exception(f"Gmail get message API error: {e}") from e

    async def list_history(
        self,
        access_token: str,
        start_history_id: str,
        page_token: Optional[str] = None,
        max_results: int = 100,
        history_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        List history records (incremental sync).

        Args:
            access_token: Valid OAuth token
            start_history_id: Starting history ID
            page_token: Pagination token
            max_results: Max number of history records
            history_types: Optional list of types ('messageAdded', 'messageDeleted', etc.)

        Returns:
            Response dict with 'history' list, 'historyId', 'nextPageToken'
        """
        params: Dict[str, Any] = {
            "startHistoryId": start_history_id,
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token
        if history_types:
            params["historyTypes"] = history_types

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{GMAIL_ROOT}/history",
                    params=params,
                    headers=self._headers(access_token),
                )
                if resp.status_code == 404:
                    return {"history": [], "historyId": start_history_id}
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"history": [], "historyId": start_history_id}
            raise Exception(f"Gmail history API error: {e}") from e
        except Exception as e:
            raise Exception(f"Gmail history API error: {e}") from e

    async def watch(
        self,
        access_token: str,
        topic_name: str,
        label_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Set up a Pub/Sub watch for push notifications.

        Args:
            access_token: Valid OAuth token
            topic_name: Full Pub/Sub topic name (projects/{project}/topics/{topic})
            label_ids: Optional list of label IDs to watch

        Returns:
            Watch response with historyId and expiration
        """
        body: Dict[str, Any] = {
            "topicName": topic_name,
        }
        if label_ids:
            body["labelIds"] = label_ids

        headers = self._headers(access_token)
        headers["Content-Type"] = "application/json"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{GMAIL_ROOT}/watch",
                    json=body,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"Gmail watch API error: {e}") from e
        except Exception as e:
            raise Exception(f"Gmail watch API error: {e}") from e

    async def stop(self, access_token: str) -> None:
        """
        Stop the current watch.

        Args:
            access_token: Valid OAuth token
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                await client.post(
                    f"{GMAIL_ROOT}/stop",
                    headers=self._headers(access_token),
                )
        except Exception as e:
            # Silently ignore errors (watch may already be stopped)
            logger.debug(f"Gmail stop watch failed (ignored): {e}")

    async def get_profile(self, access_token: str) -> Dict[str, Any]:
        """Return the authenticated user's Gmail profile (emailAddress, historyId)."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{GMAIL_ROOT}/profile",
                    headers=self._headers(access_token),
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"Gmail getProfile API error: {e}") from e
        except Exception as e:
            raise Exception(f"Gmail getProfile API error: {e}") from e

    def decode_message_body(self, payload: Dict[str, Any]) -> str:
        """
        Decode message body from Gmail API payload.

        Handles multipart messages and base64url decoding.

        Args:
            payload: Message payload from Gmail API

        Returns:
            Decoded plain text content
        """
        body = ""

        if "parts" in payload:
            # Multipart message
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        break
                elif part.get("mimeType") == "text/html" and not body:
                    # Fallback to HTML if no plain text
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        else:
            # Simple message
            data = payload.get("body", {}).get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        return body

    def extract_header(self, message: Dict[str, Any], header_name: str) -> str:
        """
        Extract a header value from a message.

        Args:
            message: Message dict from Gmail API
            header_name: Header name (case-insensitive)

        Returns:
            Header value or empty string
        """
        headers = message.get("payload", {}).get("headers", [])
        header_name_lower = header_name.lower()

        for header in headers:
            if header.get("name", "").lower() == header_name_lower:
                return header.get("value", "")

        return ""
