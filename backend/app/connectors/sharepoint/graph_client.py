"""Microsoft Graph HTTP client for SharePoint sites, libraries, files, and ACLs.

Live path: https://graph.microsoft.com/v1.0
Mock path: access token == 'dev-fixture-token' (no network, no Azure app).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from app.connectors.sharepoint.credentials import DEV_FIXTURE_TOKEN
from app.connectors.sharepoint.graph_mock import (
    FIXTURE_DRIVE_ID,
    FIXTURE_ITEM_ID,
    FIXTURE_ITEM_ID_DENIED,
    FIXTURE_SITE_ID,
    GRAPH_BASE,
    GraphThrottled,
    mock_session,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3


def graph_error_is_msa_unsupported(message: str) -> bool:
    """True when Graph refused an API because the token is a personal MSA."""
    text = (message or "").lower()
    return (
        "not supported for msa" in text
        or "no addressurl for microsoft.fileservices" in text
    )


def graph_error_is_resync_required(message: str) -> bool:
    """True when a drive delta token is expired and the crawl must restart."""
    text = (message or "").lower()
    return (
        "resyncrequired" in text
        or "resync required" in text
        or "sync state is invalid" in text
        or " failed: 410 " in text
    )

# Re-exported so existing tests keep importing from graph_client.
__all__ = [
    "GraphClient",
    "FIXTURE_DRIVE_ID",
    "FIXTURE_ITEM_ID",
    "FIXTURE_ITEM_ID_DENIED",
    "FIXTURE_SITE_ID",
    "GRAPH_BASE",
    "GraphThrottled",
    "graph_error_is_msa_unsupported",
    "graph_error_is_resync_required",
]


class GraphClient:
    """Thin async wrapper around Microsoft Graph SharePoint/Drive APIs."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._mock = mock_session()

    def set_fixture_acl_email(self, email: str) -> None:
        del email

    def set_fixture_acl_emails(self, emails: List[str]) -> None:
        """No-op. Mock permissions come from graph_mock.py, not tenant-wide emails."""
        del emails

    def _is_fixture(self, access_token: str) -> bool:
        return str(access_token or "") == DEV_FIXTURE_TOKEN

    async def _get(self, access_token: str, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers, params=params)
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After") or 1)
                logger.warning(
                    "Graph 429 throttled url=%s retry_after=%s attempt=%s",
                    url,
                    retry_after,
                    attempt + 1,
                )
                last_error = GraphThrottled(retry_after, url)
                await asyncio.sleep(retry_after)
                continue
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Graph GET {url} failed: {response.status_code} {response.text[:400]}"
                )
            data = response.json()
            if "/me/drive" in url and "/items" not in url:
                logger.info(
                    "Graph GET /me/drive HTTP %s id=%s name=%s driveType=%s",
                    response.status_code,
                    data.get("id"),
                    data.get("name"),
                    data.get("driveType"),
                )
            elif "/root/delta" in url or url.rstrip("/").endswith("/delta"):
                items = list(data.get("value") or [])
                names = [str(i.get("name") or "") for i in items[:20]]
                logger.info(
                    "Graph GET drive delta HTTP %s item_count=%s names=%s",
                    response.status_code,
                    len(items),
                    names,
                )
            return data
        raise last_error or RuntimeError(f"Graph GET {url} failed after retries")

    async def list_sites(
        self,
        access_token: str,
        search: str = "*",
        next_link: Optional[str] = None,
        site_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self._is_fixture(access_token):
            return self._mock.list_sites(site_url=site_url)
        if next_link:
            return await self._get(access_token, next_link)
        if site_url:
            hostname, _, path = site_url.replace("https://", "").replace("http://", "").partition("/")
            hostname = hostname.split("/")[0]
            site_path = "/" + path.strip("/") if path.strip("/") else ""
            encoded = quote(f"{hostname}:{site_path}", safe="")
            try:
                return {"value": [await self._get(access_token, f"{GRAPH_BASE}/sites/{encoded}")]}
            except RuntimeError as exc:
                if graph_error_is_msa_unsupported(str(exc)):
                    logger.info(
                        "Graph GET /sites skipped: not supported for this Microsoft account"
                    )
                    return {"value": []}
                raise
        try:
            return await self._get(
                access_token,
                f"{GRAPH_BASE}/sites",
                params={"search": search, "$select": "id,displayName,webUrl,name"},
            )
        except RuntimeError as exc:
            # Personal MSA tokens cannot call GET /sites; OneDrive is /me/drive.
            if graph_error_is_msa_unsupported(str(exc)):
                logger.info(
                    "Graph GET /sites skipped: not supported for this Microsoft account"
                )
                return {"value": []}
            raise

    async def list_drives(self, access_token: str, site_id: str) -> Dict[str, Any]:
        if self._is_fixture(access_token):
            return self._mock.list_drives(site_id)
        return await self._get(
            access_token,
            f"{GRAPH_BASE}/sites/{site_id}/drives",
            params={"$select": "id,name,webUrl,driveType"},
        )

    async def get_my_drive(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Personal OneDrive. ``GET /sites`` is not valid for MSA accounts."""
        if self._is_fixture(access_token):
            return None
        return await self._get(
            access_token,
            f"{GRAPH_BASE}/me/drive",
            params={"$select": "id,name,webUrl,driveType"},
        )

    async def list_drive_delta(
        self,
        access_token: str,
        drive_id: str,
        url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self._is_fixture(access_token):
            try:
                return self._mock.list_drive_delta(drive_id, url)
            except GraphThrottled as exc:
                logger.warning(
                    "Graph 429 throttled url=%s retry_after=%s attempt=1",
                    exc.url,
                    exc.retry_after,
                )
                await asyncio.sleep(exc.retry_after)
                logger.info("Graph retry after 429 url=%s", exc.url)
                return self._mock.list_drive_delta(drive_id, url)
        target = url or f"{GRAPH_BASE}/drives/{drive_id}/root/delta"
        return await self._get(access_token, target)

    async def list_permissions(
        self, access_token: str, drive_id: str, item_id: str
    ) -> List[Dict[str, Any]]:
        if self._is_fixture(access_token):
            return self._mock.list_permissions(drive_id, item_id)
        data = await self._get(
            access_token,
            f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/permissions",
        )
        return list(data.get("value") or [])

    async def list_group_members(self, access_token: str, group_id: str) -> List[Dict[str, Any]]:
        if not group_id:
            return []
        members: List[Dict[str, Any]] = []
        url: Optional[str] = (
            None
            if self._is_fixture(access_token)
            else (
                f"{GRAPH_BASE}/groups/{group_id}/members"
                "?$select=id,displayName,mail,userPrincipalName"
            )
        )
        while True:
            if self._is_fixture(access_token):
                data = self._mock.list_group_members(group_id, url)
            else:
                try:
                    data = await self._get(access_token, url or "")
                except RuntimeError as exc:
                    status = str(exc)
                    if " 401 " in f" {status} " or " 403 " in f" {status} " or status.endswith("401") or "failed: 403" in status or "failed: 401" in status:
                        logger.info(
                            "SharePoint group members denied group=%s err=%s (fail closed, no expansion)",
                            group_id,
                            status[:180],
                        )
                        return members
                    raise
            members.extend(data.get("value") or [])
            url = data.get("@odata.nextLink")
            if not url or len(members) >= 200:
                break
        return members

    async def download_content(self, access_token: str, drive_id: str, item_id: str) -> bytes:
        if self._is_fixture(access_token):
            return self._mock.download_content(drive_id, item_id)
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Graph download failed: {response.status_code} {response.text[:200]}"
                )
            return response.content
