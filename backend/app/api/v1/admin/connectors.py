"""Org-wide connector configuration (Glean-style connector management)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant, get_tenant_session, require_admin
from app.models.tenant_connector import TenantConnector
from app.services.admin.audit_logger import client_ip, write_audit_log
from app.services.tenant_resolver import TenantRouting
from app.storage.vault_client import vault_client

router = APIRouter(prefix="/connectors", tags=["admin-connectors"])

_SECRET_CONFIG_KEYS = {"password", "client_secret", "refresh_token", "secret", "api_key"}


class UpsertConnectorRequest(BaseModel):
    source_type: str
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)
    credentials: Optional[Dict[str, Any]] = None


class ConnectorResponse(BaseModel):
    source_type: str
    enabled: bool
    config: Dict[str, Any]
    setup_by: str
    credential_ref: Optional[str] = None
    tenant_id: str


def _as_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")


def _public_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in (config or {}).items() if k not in _SECRET_CONFIG_KEYS}


def _to_response(row: TenantConnector) -> ConnectorResponse:
    return ConnectorResponse(
        source_type=row.source_type,
        enabled=row.enabled,
        config=dict(row.config or {}),
        setup_by=str(row.setup_by),
        credential_ref=row.credential_ref,
        tenant_id=str(row.tenant_id),
    )


@router.post("", response_model=ConnectorResponse)
async def upsert_connector(
    body: UpsertConnectorRequest,
    request: Request,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """
    Enable or configure a connector for the entire tenant.

    Per-user OAuth is still required; this stores org config and optional
    admin-provisioned credentials (Vault pointer only).
    """
    if not body.source_type.strip():
        raise HTTPException(status_code=400, detail="source_type is required")

    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    actor_id = _as_uuid(str(admin.get("sub")), "principal_id")
    source_type = body.source_type.strip()
    public_config = _public_config(body.config)

    credential_ref = None
    creds = body.credentials or {
        k: body.config[k] for k in _SECRET_CONFIG_KEYS if k in (body.config or {})
    }
    if creds:
        credential_ref = f"kv/tenant-{tenant_id}/connector-{source_type}"
        await vault_client.set_secret(credential_ref, json.dumps(creds))

    result = await db_session.execute(
        select(TenantConnector).where(
            TenantConnector.tenant_id == tenant_id,
            TenantConnector.source_type == source_type,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = TenantConnector(
            tenant_id=tenant_id,
            source_type=source_type,
            enabled=body.enabled,
            config=public_config,
            setup_by=actor_id,
            credential_ref=credential_ref,
        )
        db_session.add(row)
        action = "connector.enabled"
    else:
        row.enabled = body.enabled
        row.config = public_config
        row.setup_by = actor_id
        if credential_ref:
            row.credential_ref = credential_ref
        action = "connector.updated"

    await write_audit_log(
        db_session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type=action,
        target={"source_type": source_type, "enabled": body.enabled},
        ip_address=client_ip(request),
    )
    await db_session.commit()
    await db_session.refresh(row)
    return _to_response(row)


@router.get("", response_model=List[ConnectorResponse])
async def list_connectors(
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    result = await db_session.execute(
        select(TenantConnector)
        .where(TenantConnector.tenant_id == tenant_id)
        .order_by(TenantConnector.source_type)
    )
    return [_to_response(row) for row in result.scalars().all()]


@router.delete("/{source_type}", response_model=ConnectorResponse)
async def remove_connector(
    source_type: str,
    request: Request,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    actor_id = _as_uuid(str(admin.get("sub")), "principal_id")

    result = await db_session.execute(
        select(TenantConnector).where(
            TenantConnector.tenant_id == tenant_id,
            TenantConnector.source_type == source_type,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Connector not configured: {source_type}")

    snapshot = _to_response(row)
    await db_session.delete(row)
    await write_audit_log(
        db_session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type="connector.removed",
        target={"source_type": source_type},
        ip_address=client_ip(request),
    )
    await db_session.commit()
    snapshot.enabled = False
    return snapshot
