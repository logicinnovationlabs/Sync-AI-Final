"""Persist admin-console audit events (Block N)."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.models.audit_log import AuditLog


def client_ip(request: Optional[Request]) -> Optional[str]:
    """Best-effort client IP from X-Forwarded-For or the ASGI client host."""
    if request is None:
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client is not None:
        return (request.client.host or "")[:64]
    return None


async def write_audit_log(
    db_session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    action_type: str,
    target: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """
    Insert an audit row. Caller is responsible for committing (same transaction
    as the admin mutation).
    """
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type=action_type,
        target_json=target,
        ip_address=ip_address,
    )
    db_session.add(entry)
    await db_session.flush()
    return entry
