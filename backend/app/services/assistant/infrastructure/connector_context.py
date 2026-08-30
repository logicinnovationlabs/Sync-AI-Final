"""Connected-connector summary for chat grounding (meta questions about integrations)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.connectors import provider_registry
from app.connectors.google import status_store
from app.connectors.google.keys import cursor_scope_id, google_oauth_token_key
from app.connectors.google.token_store import PersistentGoogleTokenStore
from app.connectors.microsoft.keys import microsoft_oauth_token_key
from app.connectors.microsoft.token_store import PersistentMicrosoftTokenStore
from app.services.cursor_store import cursor_store

logger = logging.getLogger(__name__)

_APP_NAME = "SynQ AI"

_PERSONAL_SOURCES: tuple[tuple[str, str], ...] = (
    ("google_drive", "Google Drive"),
    ("google_gmail", "Gmail"),
    ("onedrive", "OneDrive"),
    ("outlook", "Outlook"),
)


def _microsoft_mailbox(tenant_id: str, user_id: str) -> str:
    store = PersistentMicrosoftTokenStore(tenant_id)
    for key in (microsoft_oauth_token_key(tenant_id, user_id), microsoft_oauth_token_key(tenant_id)):
        blob = store.get_token(key) or {}
        email = str(blob.get("mailbox_email") or "").strip()
        if email:
            return email
    return ""


def _google_mailbox(tenant_id: str, user_id: str) -> str:
    store = PersistentGoogleTokenStore(tenant_id)
    for key in (
        google_oauth_token_key(tenant_id, user_id, "personal"),
        google_oauth_token_key(tenant_id, "", "personal"),
    ):
        blob = store.get_token(key) or {}
        email = str(blob.get("mailbox_email") or "").strip()
        if email:
            return email
    return ""


async def _source_snapshot(
    tenant_id: str,
    user_id: str,
    source_type: str,
    label: str,
    *,
    mailbox_email: str = "",
) -> Optional[Dict[str, Any]]:
    scope_id = cursor_scope_id(tenant_id, user_id)
    runtime_raw = status_store.get_status_raw(tenant_id, source_type, user_id=user_id)
    runtime = runtime_raw if runtime_raw is not None else status_store.get_status(
        tenant_id, source_type, user_id=user_id
    )
    cursor = await cursor_store.get_cursor(scope_id, source_type)

    plugin = provider_registry.get_by_source(source_type)
    has_token = False
    if plugin and getattr(plugin, "has_token", None):
        has_token = bool(plugin.has_token(tenant_id, user_id))
    elif source_type in ("google_drive", "google_gmail"):
        gstore = PersistentGoogleTokenStore(tenant_id)
        has_token = gstore.get_token(
            google_oauth_token_key(tenant_id, user_id, "personal")
        ) is not None or gstore.get_token(
            google_oauth_token_key(tenant_id, "", "personal")
        ) is not None

    if runtime_raw is None:
        if cursor:
            connection_status = "active"
        elif has_token:
            connection_status = "syncing"
        else:
            connection_status = "not_connected"
    else:
        connection_status = str(runtime.get("connection_status") or "not_connected")

    linked = has_token or bool(cursor) or connection_status not in (
        "not_connected",
        "",
    )
    if not linked:
        return None

    files_indexed = int(runtime.get("files_indexed") or 0)
    return {
        "label": label,
        "source_type": source_type,
        "status": connection_status,
        "files_indexed": files_indexed,
        "mailbox_email": mailbox_email,
        "has_sync_cursor": bool(cursor),
    }


async def build_connector_summary(tenant_id: str, user_id: str) -> str:
    """Human-readable inventory of this user's connected integrations."""
    if not tenant_id or not user_id:
        return f"No {_APP_NAME} connector data (missing tenant/user)."

    ms_mailbox = _microsoft_mailbox(tenant_id, user_id)
    google_mailbox = _google_mailbox(tenant_id, user_id)

    snapshots: List[Dict[str, Any]] = []
    for source_type, label in _PERSONAL_SOURCES:
        mailbox = ms_mailbox if source_type in ("onedrive", "outlook") else google_mailbox
        row = await _source_snapshot(
            tenant_id, user_id, source_type, label, mailbox_email=mailbox
        )
        if row:
            snapshots.append(row)

    if not snapshots:
        return (
            f"No personal connectors are linked to {_APP_NAME} for this account yet. "
            "Connect Google or Microsoft from the Connectors page to index mail and files."
        )

    lines: List[str] = [
        f"This workspace is indexed by {_APP_NAME}. Connected integrations for the signed-in user:"
    ]

    ms_rows = [r for r in snapshots if r["source_type"] in ("onedrive", "outlook")]
    google_rows = [r for r in snapshots if r["source_type"].startswith("google_")]

    if ms_rows:
        indexed = sum(r["files_indexed"] for r in ms_rows)
        statuses = {r["status"] for r in ms_rows}
        status = "active" if "active" in statuses else next(iter(statuses), "connected")
        services = ", ".join(r["label"] for r in ms_rows)
        account = ms_rows[0].get("mailbox_email") or ""
        account_bit = f" as {account}" if account else ""
        lines.append(
            f"- Microsoft 365 ({services}){account_bit}: {status}, "
            f"{indexed} item(s) indexed in {_APP_NAME}"
        )

    for row in google_rows:
        account = str(row.get("mailbox_email") or "")
        account_bit = f" as {account}" if account else ""
        lines.append(
            f"- {row['label']}{account_bit}: {row['status']}, "
            f"{row['files_indexed']} item(s) indexed in {_APP_NAME}"
        )

    lines.append(
        "Use this section to answer questions about which apps are connected, "
        "which account is linked, and whether data has been indexed."
    )
    return "\n".join(lines)
