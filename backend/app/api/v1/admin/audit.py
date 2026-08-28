"""Paginated admin audit log (Block N). Indexed on (tenant_id, created_at)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant, get_tenant_session, require_admin
from app.models.audit_log import AuditLog
from app.services.tenant_resolver import TenantRouting


router = APIRouter(prefix="/audit", tags=["admin-audit"])


class AuditLogItem(BaseModel):
    id: str
    actor_id: str
    action_type: str
    target_json: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: List[AuditLogItem]
    page: int
    page_size: int
    total: int


@router.get("", response_model=AuditLogPage)
async def list_audit_logs(
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    action_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """List this tenant's audit events. Filters never accept a tenant_id body field."""
    # audit_logs.tenant_id is VARCHAR(255); coerce at this boundary so asyncpg binds a str
    tenant_id = str(tenant.tenant_id)

    filters = [AuditLog.tenant_id == tenant_id]
    if date_from is not None:
        filters.append(AuditLog.created_at >= date_from)
    if date_to is not None:
        filters.append(AuditLog.created_at <= date_to)
    if action_type:
        filters.append(AuditLog.action_type == action_type)

    total = (
        await db_session.execute(select(func.count()).select_from(AuditLog).where(*filters))
    ).scalar_one()

    stmt = (
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db_session.execute(stmt)).scalars().all()
    return AuditLogPage(
        items=[
            AuditLogItem(
                id=str(row.id),
                actor_id=str(row.actor_id),
                action_type=row.action_type,
                target_json=row.target_json,
                ip_address=row.ip_address,
                created_at=row.created_at,
            )
            for row in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
