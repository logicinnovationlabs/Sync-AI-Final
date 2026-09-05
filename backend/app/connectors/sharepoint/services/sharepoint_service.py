"""
SharePoint connector — Microsoft Graph.

Implements BaseConnector so the blind orchestrator (sync.py) never imports
this module by name. Source tag is ``sharepoint``. Canonical IDs are
``sharepoint_{driveId}:{itemId}`` so dual-ID stripping of the ``sharepoint_``
prefix (already in acl/filter.py) works from day one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.base_connector import (
    BaseConnector,
    TokenStore,
    DeltaResult,
    DeletionResult,
    UnifiedDocument,
)
from app.connectors.sharepoint.graph_client import GraphClient, graph_error_is_resync_required
from app.connectors.sharepoint.content import extract_sharepoint_text, is_folder
from app.connectors.sharepoint.credentials import get_sharepoint_access_token

logger = logging.getLogger(__name__)


class SharePointConnector(BaseConnector):
    def __init__(self, config: Dict[str, Any], token_store: TokenStore):
        super().__init__(config, token_store)
        self.tenant_id = config.get("tenant_id")
        self.connection_scope = str(config.get("connection_scope") or "personal")
        self.site_url = str(config.get("site_url") or "").strip() or None
        self.connected_by_email = str(config.get("connected_by_email") or config.get("mailbox_email") or "")
        self.fixture_acl_emails = [
            str(e).strip() for e in (config.get("fixture_acl_emails") or []) if str(e).strip()
        ]
        self.oauth_manager = None
        self.graph_client = GraphClient()
        # Mock Graph ACLs come from graph_mock.py, not tenant-wide email lists.
        self._group_member_cache: Dict[str, List[Dict[str, Any]]] = {}

    def get_source_type(self) -> str:
        return "sharepoint"

    async def get_valid_token(self) -> str:
        token, _info = await get_sharepoint_access_token(
            str(self.tenant_id),
            self.connection_scope,
            oauth_manager=self.oauth_manager,
        )
        return token

    async def fetch_delta(self, since: datetime, cursor: Optional[str]) -> DeltaResult:
        del since
        token = await self.get_valid_token()
        state = _decode_cursor(cursor)
        if "drives" not in state:
            state["drives"] = await self._enumerate_drives(token)
            state["drive_idx"] = 0
            state["next_link"] = None
            state["delta_idx"] = 0
            state.setdefault("delta_links", {})

        drives = state.get("drives") or []
        if not drives:
            return DeltaResult(documents=[], next_cursor=None, has_more=False)

        idx = int(state.get("drive_idx") or 0)
        if idx >= len(drives):
            return await self._fetch_after_initial_crawl(token, state)
        return await self._fetch_drive_page(
            token, state, drive=drives[idx], idx=idx, idx_key="drive_idx", n_drives=len(drives)
        )

    async def _fetch_after_initial_crawl(self, token: str, state: Dict[str, Any]) -> DeltaResult:
        drives = state.get("drives") or []
        live = await self._enumerate_drives(token)
        live_ids = [str(d.get("id") or "") for d in live]
        stored_ids = [str(d.get("id") or "") for d in drives]
        if live and live_ids != stored_ids:
            logger.info(
                "SharePoint drive set changed scope=%s stored=%s live=%s; restarting crawl",
                self.connection_scope,
                stored_ids,
                live_ids,
            )
            links = dict(state.get("delta_links") or {})
            state["drives"] = live
            state["drive_idx"] = 0
            state["delta_idx"] = 0
            state["next_link"] = None
            state["delta_links"] = {did: links[did] for did in live_ids if did in links}
            return await self._fetch_drive_page(
                token,
                state,
                drive=live[0],
                idx=0,
                idx_key="drive_idx",
                n_drives=len(live),
            )
        return await self._fetch_incremental_page(token, state)

    async def _fetch_incremental_page(self, token: str, state: Dict[str, Any]) -> DeltaResult:
        drives = state.get("drives") or []
        links = dict(state.get("delta_links") or {})
        drive_ids = [str(d.get("id") or "") for d in drives if str(d.get("id") or "") in links]
        if not drive_ids:
            return DeltaResult(
                documents=[], next_cursor=json.dumps(state), has_more=False
            )
        d_idx = int(state.get("delta_idx") or 0)
        if d_idx >= len(drive_ids):
            d_idx = 0
            state["delta_idx"] = 0
            state["next_link"] = None
        drive_id = drive_ids[d_idx]
        drive = next((d for d in drives if str(d.get("id") or "") == drive_id), {"id": drive_id})
        url = state.get("next_link") or links.get(drive_id)
        try:
            page = await self.graph_client.list_drive_delta(token, drive_id, url=url)
        except RuntimeError as exc:
            if graph_error_is_resync_required(str(exc)):
                logger.warning(
                    "SharePoint delta expired drive=%s; restarting that library", drive_id
                )
                links.pop(drive_id, None)
                state["delta_links"] = links
                restart_idx = next(
                    (i for i, d in enumerate(drives) if str(d.get("id") or "") == drive_id),
                    0,
                )
                state["drive_idx"] = restart_idx
                state["next_link"] = None
                return await self._fetch_drive_page(
                    token,
                    state,
                    drive=drive,
                    idx=restart_idx,
                    idx_key="drive_idx",
                    n_drives=len(drives),
                )
            raise
        logger.info(
            "SharePoint incremental delta drive=%s item_count=%s",
            drive_id,
            len(page.get("value") or []),
        )
        return await self._delta_page_result(
            token, state, drive, page, idx=d_idx, idx_key="delta_idx", n_drives=len(drive_ids)
        )

    async def _fetch_drive_page(
        self,
        token: str,
        state: Dict[str, Any],
        *,
        drive: Dict[str, Any],
        idx: int,
        idx_key: str,
        n_drives: int,
    ) -> DeltaResult:
        page = await self.graph_client.list_drive_delta(
            token, drive["id"], url=state.get("next_link")
        )
        return await self._delta_page_result(
            token, state, drive, page, idx=idx, idx_key=idx_key, n_drives=n_drives
        )

    async def _delta_page_result(
        self,
        token: str,
        state: Dict[str, Any],
        drive: Dict[str, Any],
        page: Dict[str, Any],
        *,
        idx: int,
        idx_key: str,
        n_drives: int,
    ) -> DeltaResult:
        raw_items = list(page.get("value") or [])
        deleted_ids = [
            _item_source_id(drive, item)
            for item in raw_items
            if item.get("@removed") and item.get("id")
        ]
        files = [
            _normalize_item(item, drive)
            for item in raw_items
            if not item.get("@removed") and not is_folder(item)
        ]
        if files:
            files = await self._hydrate_files(token, files)

        next_link = page.get("@odata.nextLink")
        delta_link = page.get("@odata.deltaLink")
        if next_link:
            state["next_link"] = next_link
            has_more = True
        else:
            if delta_link:
                state.setdefault("delta_links", {})[str(drive.get("id") or "")] = delta_link
            state["next_link"] = None
            state[idx_key] = idx + 1
            has_more = int(state[idx_key]) < n_drives

        return DeltaResult(
            documents=files,
            next_cursor=json.dumps(state),
            has_more=has_more,
            deleted_ids=deleted_ids,
        )

    async def fetch_deleted_ids(self, since: datetime, cursor: Optional[str]) -> DeletionResult:
        del since
        # Graph drive delta is one stream of adds and deletes. Deletions are
        # returned on DeltaResult.deleted_ids from fetch_delta so this pass
        # must not consume the same delta token.
        return DeletionResult(deleted_ids=[], next_cursor=cursor, has_more=False)

    async def transform(self, raw_documents: List[Dict[str, Any]]) -> List[UnifiedDocument]:
        unified: List[UnifiedDocument] = []
        for item in raw_documents:
            file_id = item.get("id")
            if not file_id:
                continue
            permissions = await self._resolve_permissions(item)
            mime_type = item.get("mimeType") or ""
            owners = item.get("createdBy") or {}
            owner_user = owners.get("user") or {}
            unified.append(
                UnifiedDocument(
                    id=str(file_id),
                    title=item.get("name") or "Untitled",
                    content=item.get("_extracted_text") or item.get("name") or "",
                    source_type=self.get_source_type(),
                    url=item.get("webViewLink") or item.get("webUrl") or "",
                    permissions=permissions,
                    created_at=self._parse_timestamp(item.get("createdTime") or item.get("createdDateTime")),
                    updated_at=datetime.utcnow(),
                    source_updated_at=self._parse_timestamp(
                        item.get("modifiedTime") or item.get("lastModifiedDateTime")
                    ),
                    structured_metadata={
                        "mime_type": mime_type,
                        "file_extension": _extension(item.get("name") or ""),
                        "owner_email": owner_user.get("email") or owner_user.get("userPrincipalName") or "",
                        "site_id": item.get("_site_id") or "",
                        "site_name": item.get("_site_name") or "",
                        "drive_id": item.get("_drive_id") or "",
                        "parent_folder_id": (item.get("parentReference") or {}).get("id") or "",
                        "web_view_link": item.get("webViewLink") or item.get("webUrl") or "",
                        "size_bytes": int(item.get("size") or 0),
                    },
                )
            )
        return unified

    async def _enumerate_drives(self, token: str) -> List[Dict[str, Any]]:
        drives: List[Dict[str, Any]] = []
        try:
            drives.extend(await self._enumerate_site_drives(token))
        except Exception:
            logger.warning(
                "SharePoint list_sites failed scope=%s; continuing with /me/drive if personal",
                self.connection_scope,
                exc_info=True,
            )
        if self.connection_scope != "organization":
            await self._append_my_drive(token, drives)
        logger.info(
            "SharePoint drives enumerated scope=%s n=%s names=%s site_ids=%s",
            self.connection_scope,
            len(drives),
            [d.get("name") for d in drives],
            [d.get("site_id") or "(onedrive)" for d in drives],
        )
        return drives

    async def _enumerate_site_drives(self, token: str) -> List[Dict[str, Any]]:
        drives: List[Dict[str, Any]] = []
        next_link: Optional[str] = None
        while True:
            page = await self.graph_client.list_sites(
                token, next_link=next_link, site_url=self.site_url
            )
            for site in page.get("value") or []:
                site_id = site.get("id")
                if not site_id:
                    continue
                try:
                    drive_page = await self.graph_client.list_drives(token, site_id)
                except Exception:
                    logger.warning("list_drives failed site=%s", site_id)
                    continue
                for drive in drive_page.get("value") or []:
                    if not drive.get("id"):
                        continue
                    drives.append(
                        {
                            "id": drive["id"],
                            "name": drive.get("name") or "",
                            "site_id": site_id,
                            "site_name": site.get("displayName") or site.get("name") or "",
                            "web_url": drive.get("webUrl") or site.get("webUrl") or "",
                        }
                    )
            next_link = page.get("@odata.nextLink")
            if not next_link or self.site_url:
                break
        return drives

    async def _append_my_drive(self, token: str, drives: List[Dict[str, Any]]) -> None:
        try:
            mine = await self.graph_client.get_my_drive(token)
        except Exception:
            logger.warning("GET /me/drive failed", exc_info=True)
            raise
        drive_id = str((mine or {}).get("id") or "")
        if not drive_id:
            return
        if any(str(d.get("id") or "") == drive_id for d in drives):
            return
        drives.append(
            {
                "id": drive_id,
                "name": mine.get("name") or "OneDrive",
                "site_id": "",
                "site_name": "OneDrive",
                "web_url": mine.get("webUrl") or "",
            }
        )
        logger.info("SharePoint personal OneDrive drive_id=%s name=%s", drive_id, mine.get("name"))

    async def _hydrate_files(self, access_token: str, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        semaphore = asyncio.Semaphore(5)

        async def _one(item: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                drive_id = item.get("_drive_id") or ""
                graph_item_id = str(item.get("id") or "").split(":")[-1]
                try:
                    perms = await self.graph_client.list_permissions(
                        access_token, drive_id, graph_item_id
                    )
                    if not perms:
                        inherited = item.get("inheritedFrom") or {}
                        parent_id = str(inherited.get("id") or "")
                        if parent_id:
                            logger.info(
                                "SharePoint inheritedFrom parent walk item=%s parent=%s",
                                graph_item_id,
                                parent_id,
                            )
                            perms = await self.graph_client.list_permissions(
                                access_token, drive_id, parent_id
                            )
                    item["permissions"] = await self._expand_group_permissions(access_token, perms)
                except Exception:
                    logger.warning("permissions.list failed item_id=%s; compiling with empty ACL", item.get("id"))
                    item["permissions"] = []
                item["_extracted_text"] = await extract_sharepoint_text(
                    self.graph_client, access_token, item
                )
                return item

        if not files:
            return files
        return list(await asyncio.gather(*[_one(f) for f in files]))

    async def _expand_group_permissions(
        self, access_token: str, permissions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        expanded = list(permissions)
        for perm in list(permissions):
            identity = _granted_identity(perm)
            group = identity.get("group") or identity.get("siteGroup") or {}
            group_id = str(group.get("id") or "")
            if not group_id:
                continue
            members = self._group_member_cache.get(group_id)
            if members is None:
                try:
                    members = await self.graph_client.list_group_members(access_token, group_id)
                except Exception:
                    logger.info("SharePoint group member expansion failed group=%s (fail closed)", group_id)
                    members = []
                self._group_member_cache[group_id] = members
            for member in members:
                email = member.get("mail") or member.get("userPrincipalName")
                if not email:
                    continue
                expanded.append(
                    {
                        "id": f"{perm.get('id')}:{member.get('id')}",
                        "roles": perm.get("roles") or ["read"],
                        "grantedToV2": {
                            "user": {
                                "id": member.get("id"),
                                "email": email,
                                "displayName": member.get("displayName"),
                            }
                        },
                    }
                )
        return expanded

    async def _resolve_permissions(self, item: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        skipped = 0
        for perm in item.get("permissions") or []:
            identity = _granted_identity(perm)
            user = identity.get("user") or {}
            email = user.get("email") or user.get("userPrincipalName") or ""
            link = perm.get("link") or {}
            if link.get("scope") in {"anonymous", "organization", "users"}:
                skipped += 1
                continue
            if email:
                out.append(f"user:{email}")
            elif identity.get("group") or identity.get("siteGroup"):
                skipped += 1
        if skipped:
            logger.info("skipped %s non-user SharePoint permission(s) item=%s", skipped, item.get("id"))
        if not out:
            created = ((item.get("createdBy") or {}).get("user") or {})
            email = created.get("email") or created.get("userPrincipalName")
            if email:
                out.append(f"user:{email}")
        return out

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> datetime:
        if not timestamp_str:
            return datetime.utcnow()
        clean_ts = re.sub(r"[+-]\d{2}:\d{2}$|Z$", "", str(timestamp_str))
        try:
            return datetime.fromisoformat(clean_ts)
        except ValueError:
            return datetime.utcnow()


def _decode_cursor(cursor: Optional[str]) -> Dict[str, Any]:
    if not cursor:
        return {}
    try:
        data = json.loads(cursor)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def _item_source_id(drive: Dict[str, Any], item: Dict[str, Any]) -> str:
    item_id = str(item.get("id") or "")
    drive_id = str(drive.get("id") or item.get("_drive_id") or "")
    if ":" in item_id and not drive_id:
        return item_id
    return f"{drive_id}:{item_id}" if drive_id else item_id


def _normalize_item(item: Dict[str, Any], drive: Dict[str, Any]) -> Dict[str, Any]:
    source_id = _item_source_id(drive, item)
    file_obj = item.get("file") or {}
    item["id"] = source_id
    item["createdTime"] = item.get("createdDateTime")
    item["modifiedTime"] = item.get("lastModifiedDateTime")
    item["webViewLink"] = item.get("webUrl") or drive.get("web_url") or ""
    item["mimeType"] = file_obj.get("mimeType") or item.get("mimeType") or ""
    item["_drive_id"] = drive.get("id")
    item["_site_id"] = drive.get("site_id")
    item["_site_name"] = drive.get("site_name")
    return item


def _extension(name: str) -> str:
    if "." in name:
        return name.rsplit(".", 1)[-1].lower()
    return ""


def _granted_identity(perm: Dict[str, Any]) -> Dict[str, Any]:
    return (
        perm.get("grantedToV2")
        or perm.get("grantedTo")
        or ((perm.get("grantedToIdentitiesV2") or [{}])[0] if perm.get("grantedToIdentitiesV2") else {})
        or ((perm.get("grantedToIdentities") or [{}])[0] if perm.get("grantedToIdentities") else {})
        or {}
    )
