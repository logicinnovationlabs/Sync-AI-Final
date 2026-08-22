"""Storage keys for Google OAuth tokens (per tenant user)."""

from __future__ import annotations

from typing import Optional


def google_oauth_token_key(tenant_id: str, user_id: str = "") -> str:
    """Redis/vault token key. Per-user when ``user_id`` is set."""
    tid = str(tenant_id or "").strip()
    uid = str(user_id or "").strip()
    if uid:
        return f"google_oauth:{tid}:{uid}"
    return f"google_oauth:{tid}"


def tenant_from_token_key(key: str) -> Optional[str]:
    prefix = "google_oauth:"
    if not key.startswith(prefix):
        return None
    rest = key[len(prefix) :]
    return rest.split(":")[0] if rest else None


def principal_from_token_key(key: str) -> str:
    prefix = "google_oauth:"
    if not key.startswith(prefix):
        return ""
    parts = key[len(prefix) :].split(":")
    return parts[1] if len(parts) > 1 else ""


def vault_google_oauth_key(tenant_id: str, user_id: str = "") -> str:
    uid = str(user_id or "").strip()
    if uid:
        return f"kv/tenant-{tenant_id}/google-oauth/{uid}"
    return f"kv/tenant-{tenant_id}/google-oauth"


def cursor_scope_id(tenant_id: str, user_id: str = "") -> str:
    """sync_cursors PK is (tenant_id, source_type); encode user into tenant_id."""
    uid = str(user_id or "").strip()
    if uid:
        return f"{tenant_id}:{uid}"
    return str(tenant_id)
