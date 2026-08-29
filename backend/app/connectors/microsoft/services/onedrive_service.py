"""OneDrive connector — backfill via delta, incremental via stored deltaLink."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.connectors.microsoft.clients.graph_client import GraphClient
from app.connectors.microsoft.content import extract_onedrive_text
from app.connectors.microsoft.oauth import MicrosoftOAuthManager
from app.core.base_connector import (
    BaseConnector,
    DeletionResult,
    DeltaResult,
    TokenStore,
    UnifiedDocument,
)


class OneDriveConnector(BaseConnector):
    def __init__(
        self,
        config: Dict[str, Any],
        token_store: TokenStore,
        oauth_manager: Optional[MicrosoftOAuthManager] = None,
    ):
        super().__init__(config, token_store)
        self.tenant_id = config.get("tenant_id")
        self.oauth_manager = oauth_manager
        self.graph = GraphClient()
        self.mailbox_email = str(config.get("mailbox_email") or "")
        self.connected_by = str(config.get("connected_by") or "")

    def get_source_type(self) -> str:
        return "onedrive"

    async def get_valid_token(self) -> str:
        if not self.oauth_manager:
            raise Exception("OAuth manager not configured")
        return await self.oauth_manager.get_valid_token(self.tenant_id)

    async def fetch_delta(self, since: datetime, cursor: Optional[str]) -> DeltaResult:
        _ = since
        return await self._page_delta(cursor)

    async def fetch_since_delta_link(self, cursor: str) -> DeltaResult:
        return await self._page_delta(cursor)

    async def _page_delta(self, cursor: Optional[str]) -> DeltaResult:
        token = await self.get_valid_token()
        items, next_link, delta_link = await self.graph.list_drive_delta(token, cursor)
        deleted = [str(i["id"]) for i in items if i.get("@removed") and i.get("id")]
        docs = [i for i in items if not i.get("@removed") and i.get("folder") is None]
        # Prefer continuing nextLink; otherwise lock the deltaLink as cursor.
        if next_link:
            return DeltaResult(documents=docs, next_cursor=next_link, has_more=True)
        return DeltaResult(
            documents=docs,
            next_cursor=delta_link or cursor,
            has_more=False,
        )

    async def fetch_deleted_ids(self, since: datetime, cursor: Optional[str]) -> DeletionResult:
        _ = since
        token = await self.get_valid_token()
        items, next_link, delta_link = await self.graph.list_drive_delta(token, cursor)
        deleted = [str(i["id"]) for i in items if i.get("@removed") and i.get("id")]
        nxt = next_link or delta_link or cursor
        return DeletionResult(deleted_ids=deleted, next_cursor=nxt, has_more=bool(next_link))

    async def transform(self, raw_documents: List[Dict[str, Any]]) -> List[UnifiedDocument]:
        token = await self.get_valid_token()
        out: List[UnifiedDocument] = []
        for item in raw_documents:
            item_id = str(item.get("id") or "")
            if not item_id or item.get("folder") is not None:
                continue
            name = str(item.get("name") or "Untitled")
            content = await extract_onedrive_text(self.graph, token, item)
            mime = ""
            file_facet = item.get("file") if isinstance(item.get("file"), dict) else {}
            mime = str(file_facet.get("mimeType") or "")
            perms = self._acl()
            created = self._parse_ts(item.get("createdDateTime"))
            modified = self._parse_ts(item.get("lastModifiedDateTime"))
            out.append(
                UnifiedDocument(
                    id=f"onedrive:{item_id}",
                    title=name,
                    content=content or name,
                    source_type="onedrive",
                    url=str(item.get("webUrl") or f"https://onedrive.live.com/?id={item_id}"),
                    permissions=perms,
                    created_at=created,
                    updated_at=modified,
                    source_updated_at=modified,
                    structured_metadata={
                        "mime_type": mime,
                        "file_extension": name.rsplit(".", 1)[-1] if "." in name else "",
                        "size_bytes": int(item.get("size") or 0),
                        "web_url": item.get("webUrl") or "",
                        "parent_path": (item.get("parentReference") or {}).get("path") or "",
                        "created_by": (
                            ((item.get("createdBy") or {}).get("user") or {}).get("email")
                            or ""
                        ),
                    },
                )
            )
        return out

    def _acl(self) -> List[str]:
        # UnifiedDocument requires every permission to be "user:..." or "group:..."
        terms: List[str] = []
        if self.connected_by:
            cb = str(self.connected_by)
            terms.append(cb if cb.startswith(("user:", "group:")) else f"user:{cb}")
        if self.mailbox_email:
            terms.append(f"user:{self.mailbox_email.lower()}")
        if not terms:
            terms = [f"user:{self.tenant_id}"]
        return list(dict.fromkeys(terms))

    @staticmethod
    def _parse_ts(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                pass
        return datetime.now(timezone.utc)
