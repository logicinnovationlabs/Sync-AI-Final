"""Outlook mail connector — inbox delta backfill + webhook incremental."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.connectors.microsoft.clients.graph_client import GraphClient
from app.connectors.microsoft.oauth import MicrosoftOAuthManager
from app.core.base_connector import (
    BaseConnector,
    DeletionResult,
    DeltaResult,
    TokenStore,
    UnifiedDocument,
)


class OutlookConnector(BaseConnector):
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
        return "outlook"

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
        items, next_link, delta_link = await self.graph.list_mail_delta(token, cursor)
        docs = [i for i in items if not i.get("@removed") and not i.get("isDraft")]
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
        items, next_link, delta_link = await self.graph.list_mail_delta(token, cursor)
        deleted = [str(i["id"]) for i in items if i.get("@removed") and i.get("id")]
        return DeletionResult(
            deleted_ids=deleted,
            next_cursor=next_link or delta_link or cursor,
            has_more=bool(next_link),
        )

    async def transform(self, raw_documents: List[Dict[str, Any]]) -> List[UnifiedDocument]:
        token = await self.get_valid_token()
        out: List[UnifiedDocument] = []
        for raw in raw_documents:
            msg_id = str(raw.get("id") or "")
            if not msg_id:
                continue
            # Delta list is thin — hydrate full message when body missing.
            msg = raw
            body = raw.get("body") if isinstance(raw.get("body"), dict) else {}
            if not body.get("content") and not raw.get("bodyPreview"):
                try:
                    msg = await self.graph.get_message(token, msg_id)
                except Exception:
                    msg = raw
            subject = str(msg.get("subject") or "(no subject)")
            body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
            content = str(body.get("content") or msg.get("bodyPreview") or "")
            # Strip basic HTML tags for indexing when contentType is html.
            if str(body.get("contentType") or "").lower() == "html":
                content = _strip_html(content)
            from_email = ""
            frm = msg.get("from") if isinstance(msg.get("from"), dict) else {}
            email_addr = (frm.get("emailAddress") or {}) if isinstance(frm, dict) else {}
            from_email = str(email_addr.get("address") or "")
            to_emails = []
            for recip in msg.get("toRecipients") or []:
                ea = (recip or {}).get("emailAddress") or {}
                addr = ea.get("address")
                if addr:
                    to_emails.append(str(addr))
            received = self._parse_ts(msg.get("receivedDateTime"))
            out.append(
                UnifiedDocument(
                    id=f"outlook:{msg_id}",
                    title=subject,
                    content=content or subject,
                    source_type="outlook",
                    url=str(msg.get("webLink") or ""),
                    permissions=self._acl(),
                    created_at=received,
                    updated_at=received,
                    source_updated_at=received,
                    structured_metadata={
                        "from_email": from_email,
                        "to_emails": to_emails,
                        "conversation_id": msg.get("conversationId") or "",
                        "has_attachments": bool(msg.get("hasAttachments")),
                        "importance": msg.get("importance") or "",
                        "received_at": msg.get("receivedDateTime") or "",
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


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
