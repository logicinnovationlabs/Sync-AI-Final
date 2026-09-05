"""SharePoint Graph credentials: client-credentials (org) or delegated OAuth (member).

Mirrors Google Drive's credential_mode split:
- Google org  → service_account_dwd (Vault SA JSON + impersonation)
- SharePoint org → client_credentials (Vault app JSON: azure_tenant_id, client_id, client_secret)
- SharePoint personal → oauth (delegated token in token_store)

Vault JSON shape for org:
{
  "azure_tenant_id": "...",
  "client_id": "...",
  "client_secret": "...",
  "auth_mode": "client_credentials"
}

A secret marked with "# DEV_FIXTURE" or "dev_fixture": true never calls Microsoft —
it returns a fixture access token so the Connect/sync path is exercisable without
an Azure app registration.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from sqlalchemy import select

from app.connectors.sharepoint.keys import redis_sharepoint_app_key

logger = logging.getLogger(__name__)

MODE_CLIENT_CREDENTIALS = "client_credentials"
MODE_OAUTH = "oauth"
GRAPH_DEFAULT_SCOPE = "https://graph.microsoft.com/.default"
DEV_FIXTURE_TOKEN = "dev-fixture-token"
DEV_FIXTURE_VAULT_KEY = "kv/tenant/dev-fake-sharepoint-app"
DEV_FIXTURE_APP_SECRET = {
    "azure_tenant_id": "00000000-0000-0000-0000-000000000000",
    "client_id": "dev-fake-sharepoint-client-id",
    "client_secret": "dev-fake-sharepoint-client-secret-not-real",
    "auth_mode": "client_credentials",
    "dev_fixture": True,
    "# DEV_FIXTURE": "NOT_A_REAL_CREDENTIAL - DO_NOT_USE_IN_PRODUCTION",
}

REQUIRED_APP_KEYS = ("azure_tenant_id", "client_id", "client_secret")


def is_dev_fixture(info: Any) -> bool:
    if not isinstance(info, dict):
        return False
    if info.get("dev_fixture") is True:
        return True
    marker = info.get("# DEV_FIXTURE") or info.get("DEV_FIXTURE")
    return bool(marker)


def parse_app_secret(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    info: Any = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(info, dict):
        raise ValueError("Vault secret is not a valid JSON object")
    missing = [k for k in REQUIRED_APP_KEYS if not str(info.get(k) or "").strip()]
    if missing:
        raise ValueError(f"Vault secret missing required keys: {', '.join(missing)}")
    return info


def _sync_redis():
    try:
        from app.storage.redis_client import create_sync_redis_client

        return create_sync_redis_client()
    except Exception:
        return None


def cache_app_secret(tenant_id: str, info: Dict[str, Any]) -> None:
    """Mirror app credentials in Redis so Celery can read them under MockVault."""
    client = _sync_redis()
    if client is None:
        return
    try:
        client.set(redis_sharepoint_app_key(tenant_id), json.dumps(info))
    except Exception:
        logger.warning("Failed to cache SharePoint app secret in Redis tenant=%s", tenant_id)


def load_cached_app_secret(tenant_id: str) -> Optional[Dict[str, Any]]:
    client = _sync_redis()
    if client is None:
        return None
    try:
        raw = client.get(redis_sharepoint_app_key(tenant_id))
        if not raw:
            return None
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        info = json.loads(raw)
        return info if isinstance(info, dict) else None
    except Exception:
        return None


async def load_sharepoint_connector_row(tenant_id: str, connection_scope: str = "organization"):
    from app.core.exceptions import TenantNotFoundError
    from app.models.tenant_connector import TenantConnector
    from app.services.tenant_resolver import tenant_resolver
    from app.storage.tenant_db import tenant_db_manager

    try:
        routing = await tenant_resolver.resolve(str(tenant_id))
        factory = tenant_db_manager.get_session_factory(
            routing.db_host,
            routing.db_name,
            routing.db_user,
            routing.db_password,
            str(routing.tenant_id),
        )
        async with factory() as session:
            result = await session.execute(
                select(TenantConnector).where(
                    TenantConnector.tenant_id == routing.tenant_id,
                    TenantConnector.source_type == "sharepoint",
                    TenantConnector.connection_scope == connection_scope,
                )
            )
            return result.scalar_one_or_none()
    except TenantNotFoundError:
        return None
    except (TypeError, ValueError):
        return None
    except Exception:
        logger.exception(
            "load SharePoint connector row failed tenant=%s scope=%s", tenant_id, connection_scope
        )
        return None


async def load_app_secret(tenant_id: str, vault_key: Optional[str] = None) -> Dict[str, Any]:
    from app.storage.vault_client import vault_client

    key = (vault_key or "").strip()
    if key == DEV_FIXTURE_VAULT_KEY:
        cache_app_secret(str(tenant_id), DEV_FIXTURE_APP_SECRET)
        return dict(DEV_FIXTURE_APP_SECRET)

    if vault_key:
        try:
            raw = await vault_client.get_secret(vault_key)
            info = parse_app_secret(raw)
            cache_app_secret(str(tenant_id), info)
            return info
        except Exception as exc:
            logger.warning(
                "Vault read failed for SharePoint app secret tenant=%s key=%s: %s",
                tenant_id,
                vault_key,
                type(exc).__name__,
            )
            if is_dev_fixture(load_cached_app_secret(str(tenant_id)) or {}):
                return dict(DEV_FIXTURE_APP_SECRET)
    cached = load_cached_app_secret(str(tenant_id))
    if cached:
        return parse_app_secret(cached)
    raise RuntimeError("SharePoint app credentials not found in Vault or Redis cache")


async def mint_client_credentials_token(info: Dict[str, Any]) -> str:
    if is_dev_fixture(info):
        return DEV_FIXTURE_TOKEN

    azure_tenant = str(info["azure_tenant_id"]).strip()
    client_id = str(info["client_id"]).strip()
    client_secret = str(info["client_secret"]).strip()

    from azure.identity import ClientSecretCredential

    creds = ClientSecretCredential(
        tenant_id=azure_tenant,
        client_id=client_id,
        client_secret=client_secret,
    )
    token = creds.get_token(GRAPH_DEFAULT_SCOPE)
    if not token or not token.token:
        raise RuntimeError("Microsoft client-credentials token was empty")
    return str(token.token)


async def get_sharepoint_access_token(
    tenant_id: str,
    connection_scope: str = "organization",
    oauth_manager=None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Return (access_token, app_info_or_empty).

    app_info is populated for client_credentials so callers can detect fixture mode.
    """
    row = None
    try:
        UUID(str(tenant_id))
        row = await load_sharepoint_connector_row(tenant_id, connection_scope)
    except (TypeError, ValueError):
        row = None

    mode = MODE_OAUTH
    if row is not None:
        mode = str((row.config or {}).get("credential_mode") or "").strip().lower() or MODE_OAUTH

    if connection_scope == "organization" or mode == MODE_CLIENT_CREDENTIALS:
        vault_key = (row.credential_ref if row is not None else None)
        info = await load_app_secret(tenant_id, vault_key)
        token = await mint_client_credentials_token(info)
        return token, info

    if oauth_manager is None:
        raise RuntimeError("SharePoint personal OAuth manager is not configured")
    token = await oauth_manager.get_valid_token(tenant_id)
    return token, {}
