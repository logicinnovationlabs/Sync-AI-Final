"""Storage keys for SharePoint credentials and OAuth tokens (per tenant)."""

from __future__ import annotations

from typing import Optional


def sharepoint_oauth_token_key(
    tenant_id: str, user_id: str = "", connection_scope: str = "personal"
) -> str:
    tid = str(tenant_id or "").strip()
    uid = str(user_id or "").strip()
    scope = str(connection_scope or "personal").strip()
    if uid:
        return f"sharepoint_oauth:{tid}:{uid}:{scope}"
    return f"sharepoint_oauth:{tid}:{scope}"


def vault_sharepoint_oauth_key(
    tenant_id: str, user_id: str = "", connection_scope: str = "personal"
) -> str:
    uid = str(user_id or "").strip()
    scope = str(connection_scope or "personal").strip()
    if uid:
        return f"kv/tenant-{tenant_id}/sharepoint-oauth/{uid}/{scope}"
    return f"kv/tenant-{tenant_id}/sharepoint-oauth/{scope}"


def vault_sharepoint_app_key(tenant_id: str) -> str:
    """Default Vault key name for admin-provisioned Graph app credentials."""
    return f"kv/tenant-{tenant_id}/sharepoint-app"


def redis_sharepoint_app_key(tenant_id: str) -> str:
    """Redis mirror so MockVault (process-local) is visible to Celery workers."""
    return f"sharepoint_app_cred:{tenant_id}"


def tenant_from_token_key(key: str) -> Optional[str]:
    prefix = "sharepoint_oauth:"
    if not key.startswith(prefix):
        return None
    rest = key[len(prefix):]
    return rest.split(":")[0] if rest else None
