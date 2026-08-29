"""Microsoft Graph HTTP client (OneDrive + Outlook + subscriptions)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


class GraphClient:
    """Thin async client for Microsoft Graph."""

    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    def _headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    async def get_me(self, access_token: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{GRAPH_ROOT}/me", headers=self._headers(access_token))
            resp.raise_for_status()
            return resp.json()

    async def get_json(self, access_token: str, url: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=self._headers(access_token))
            resp.raise_for_status()
            return resp.json()

    async def list_drive_delta(
        self,
        access_token: str,
        cursor_url: Optional[str] = None,
        *,
        page_size: int = 50,
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
        """
        Page OneDrive delta.

        Returns (items, next_link, delta_link).
        Prefer following next_link until delta_link appears.
        """
        url = cursor_url or f"{GRAPH_ROOT}/me/drive/root/delta?$top={page_size}"
        data = await self.get_json(access_token, url)
        items = list(data.get("value") or [])
        next_link = data.get("@odata.nextLink")
        delta_link = data.get("@odata.deltaLink")
        return items, next_link, delta_link

    async def download_drive_item(self, access_token: str, item_id: str) -> bytes:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(
                f"{GRAPH_ROOT}/me/drive/items/{item_id}/content",
                headers=self._headers(access_token),
            )
            resp.raise_for_status()
            return resp.content

    async def list_mail_delta(
        self,
        access_token: str,
        cursor_url: Optional[str] = None,
        *,
        page_size: int = 25,
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
        url = (
            cursor_url
            or f"{GRAPH_ROOT}/me/mailFolders/inbox/messages/delta?$top={page_size}"
        )
        data = await self.get_json(access_token, url)
        items = list(data.get("value") or [])
        return items, data.get("@odata.nextLink"), data.get("@odata.deltaLink")

    async def get_message(self, access_token: str, message_id: str) -> Dict[str, Any]:
        select = (
            "id,subject,bodyPreview,body,from,toRecipients,receivedDateTime,"
            "conversationId,hasAttachments,importance,webLink,isDraft"
        )
        url = f"{GRAPH_ROOT}/me/messages/{message_id}?$select={select}"
        return await self.get_json(access_token, url)

    async def create_subscription(
        self,
        access_token: str,
        *,
        resource: str,
        notification_url: str,
        client_state: str,
        change_type: str = "created,updated,deleted",
        minutes: int = 4000,
    ) -> Dict[str, Any]:
        expiration = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        body = {
            "changeType": change_type,
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": expiration.isoformat().replace("+00:00", "Z"),
            "clientState": client_state,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{GRAPH_ROOT}/subscriptions",
                headers={**self._headers(access_token), "Content-Type": "application/json"},
                json=body,
            )
            if resp.status_code >= 400:
                logger.error("Graph subscription create failed: %s", resp.text[:400])
            resp.raise_for_status()
            return resp.json()

    async def delete_subscription(self, access_token: str, subscription_id: str) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.delete(
                f"{GRAPH_ROOT}/subscriptions/{subscription_id}",
                headers=self._headers(access_token),
            )
            if resp.status_code not in (204, 404):
                resp.raise_for_status()

    async def renew_subscription(
        self,
        access_token: str,
        subscription_id: str,
        *,
        minutes: int = 4000,
    ) -> Dict[str, Any]:
        expiration = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.patch(
                f"{GRAPH_ROOT}/subscriptions/{subscription_id}",
                headers={**self._headers(access_token), "Content-Type": "application/json"},
                json={
                    "expirationDateTime": expiration.isoformat().replace("+00:00", "Z"),
                },
            )
            resp.raise_for_status()
            return resp.json()
