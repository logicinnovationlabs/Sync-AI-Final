"""MCP tool-call audit rows on the shared audit_logs table (Block N schema)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.services.admin.audit_logger import client_ip
from app.storage.control_plane_db import ControlPlaneSessionLocal

logger = logging.getLogger(__name__)

ACTION_TYPE = "mcp.tool_call"


async def write_mcp_audit(
    *,
    tenant_id: str,
    actor_id: UUID,
    host: Optional[str],
    client: Optional[str],
    user: str,
    tool: str,
    outcome: str,
    server_name: str,
    ip_address: Optional[str] = None,
    session: Optional[AsyncSession] = None,
) -> None:
    """One row per tool call, success or failure. Never raises to the caller."""
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type=ACTION_TYPE,
        target_json={
            "host": host,
            "client": client,
            "user": user,
            "tool": tool,
            "outcome": outcome,
            "server_name": server_name,
        },
        ip_address=(ip_address or host or "")[:64] or None,
    )
    try:
        if session is not None:
            session.add(entry)
            await session.flush()
            return
        async with ControlPlaneSessionLocal() as db:
            db.add(entry)
            await db.commit()
    except Exception:
        logger.exception("MCP audit write failed tool=%s outcome=%s", tool, outcome)
