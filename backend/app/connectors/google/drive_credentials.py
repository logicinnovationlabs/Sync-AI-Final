"""Drive credential modes: admin OAuth (personal Gmail) or Workspace DWD.

source_accounts in the spec maps onto tenant_connectors: credential_ref is the
Vault key name only. Personal Drive stays on existing admin OAuth. Workspace
tenants may set credential_mode=service_account_dwd and impersonate the admin
Drive user with drive.readonly + drive.metadata.readonly.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import TenantNotFoundError

logger = logging.getLogger(__name__)

DRIVE_READONLY_SCOPES = (
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
)

MODE_OAUTH = "oauth"
MODE_DWD = "service_account_dwd"


async def _tenant_session(tenant_id: str):
    from app.services.tenant_resolver import tenant_resolver
    from app.storage.tenant_db import tenant_db_manager

    routing = await tenant_resolver.resolve(str(tenant_id))
    async for session in tenant_db_manager.get_session(
        routing.db_host,
        routing.db_name,
        routing.db_user,
        routing.db_password,
        str(routing.tenant_id),
    ):
        yield session, routing.tenant_id
        return


async def load_drive_connector_row(tenant_id: str):
    from app.models.tenant_connector import TenantConnector

    try:
        async for session, tid in _tenant_session(tenant_id):
            result = await session.execute(
                select(TenantConnector).where(
                    TenantConnector.tenant_id == tid,
                    TenantConnector.source_type == "google_drive",
                )
            )
            return result.scalar_one_or_none()
    except TenantNotFoundError:
        return None
    except (TypeError, ValueError):
        return None
    except Exception:
        logger.exception("load Drive connector row failed tenant=%s", tenant_id)
        return None
    return None


async def drive_ingest_paused(tenant_id: str) -> bool:
    row = await load_drive_connector_row(tenant_id)
    if row is None:
        return False
    return bool((row.config or {}).get("ingest_paused"))


async def set_drive_ingest_paused(tenant_id: str, paused: bool, reason: str = "") -> None:
    from app.models.tenant_connector import TenantConnector

    try:
        async for session, tid in _tenant_session(tenant_id):
            result = await session.execute(
                select(TenantConnector).where(
                    TenantConnector.tenant_id == tid,
                    TenantConnector.source_type == "google_drive",
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                logger.warning(
                    "cannot pause Drive ingest: no tenant_connectors row tenant=%s",
                    tenant_id,
                )
                return
            config = dict(row.config or {})
            config["ingest_paused"] = paused
            if reason:
                config["ingest_paused_reason"] = reason
            elif not paused:
                config.pop("ingest_paused_reason", None)
            row.config = config
            await session.commit()
            return
    except TenantNotFoundError:
        logger.warning("cannot pause Drive ingest: tenant not found tenant=%s", tenant_id)


def _credential_mode(row) -> str:
    if row is not None:
        mode = str((row.config or {}).get("credential_mode") or "").strip().lower()
        if mode:
            return mode
    return (settings.google_drive_credential_mode or MODE_OAUTH).strip().lower()


async def mint_dwd_access_token(tenant_id: str, row) -> str:
    """Impersonate the admin Drive user via a Vault-stored service-account JSON."""
    from app.storage.vault_client import vault_client

    impersonate = (
        (row.config or {}).get("impersonate_user_email") if row is not None else None
    ) or settings.google_dwd_impersonate_email
    vault_key = (
        (row.credential_ref if row is not None else None)
        or settings.google_service_account_vault_key
    )
    if not impersonate or not vault_key:
        raise RuntimeError(
            "DWD Drive auth requires impersonate_user_email and a Vault JSON key name"
        )
    raw = await vault_client.get_secret(vault_key)
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    info: Any = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(info, dict):
        raise RuntimeError("DWD Vault secret is not a service-account JSON object")

    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=list(DRIVE_READONLY_SCOPES),
        subject=str(impersonate),
    )
    creds.refresh(Request())
    token = getattr(creds, "token", None)
    if not token:
        raise RuntimeError("DWD token refresh returned empty access token")
    logger.info("Drive DWD token minted tenant=%s", tenant_id)
    return str(token)


async def get_drive_access_token(tenant_id: str, oauth_manager) -> str:
    try:
        UUID(str(tenant_id))
        uuid_tenant = True
    except (TypeError, ValueError):
        uuid_tenant = False

    row = await load_drive_connector_row(tenant_id) if uuid_tenant else None
    mode = _credential_mode(row)
    if uuid_tenant and mode == MODE_DWD:
        return await mint_dwd_access_token(tenant_id, row)
    if not oauth_manager:
        raise RuntimeError("OAuth manager not configured")
    return await oauth_manager.get_valid_token(tenant_id)
