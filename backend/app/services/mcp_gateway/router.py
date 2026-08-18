"""GET/POST /mcp/{server} — persona MCP endpoints on the existing app."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.admin.audit_logger import client_ip
from app.services.mcp_gateway.allowlist import is_tool_allowed, list_allowed_tools
from app.services.mcp_gateway.audit import write_mcp_audit
from app.services.mcp_gateway.dispatch import dispatch_tool
from app.services.mcp_gateway.identity import (
    actor_id_for_audit,
    get_mcp_identity,
    mcp_principal_id,
    mcp_tenant_id,
    reject_impersonation,
)
from app.storage.control_plane_db import get_control_plane_session

router = APIRouter(tags=["mcp-gateway"])


class ToolCallRequest(BaseModel):
    tool: str = Field(..., min_length=1)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    principal_id: Optional[str] = None


def _client_name(request: Request) -> str:
    return (
        request.headers.get("X-MCP-Client")
        or request.headers.get("User-Agent")
        or "unknown"
    )


@router.get("/mcp/{server}")
async def list_mcp_tools(
    server: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_mcp_identity),
    db: AsyncSession = Depends(get_control_plane_session),
) -> Dict[str, Any]:
    tenant_id = mcp_tenant_id(current_user)
    tools = await list_allowed_tools(db, tenant_id=tenant_id, server_name=server)
    return {"server": server, "tenant_id": tenant_id, "tools": tools}


@router.post("/mcp/{server}")
async def call_mcp_tool(
    server: str,
    body: ToolCallRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_mcp_identity),
    db: AsyncSession = Depends(get_control_plane_session),
) -> Dict[str, Any]:
    tenant_id = mcp_tenant_id(current_user)
    principal_id = mcp_principal_id(current_user)
    host = client_ip(request)
    client = _client_name(request)
    tool = body.tool
    outcome = "error"

    try:
        reject_impersonation(
            current_user,
            body_tenant_id=body.tenant_id,
            body_user_id=body.user_id or body.principal_id,
            arguments=body.arguments,
        )
        allowed = await is_tool_allowed(
            db,
            tenant_id=tenant_id,
            server_name=server,
            tool_name=tool,
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Tool not allowlisted")
        result = await dispatch_tool(
            tool_name=tool,
            arguments=body.arguments,
            tenant_id=tenant_id,
            principal_id=principal_id,
        )
        outcome = "success"
        return {"server": server, "tool": tool, "outcome": outcome, "result": result}
    except HTTPException as exc:
        outcome = "rejected" if exc.status_code in {401, 403} else "error"
        raise
    except Exception:
        outcome = "error"
        raise
    finally:
        await write_mcp_audit(
            tenant_id=tenant_id,
            actor_id=actor_id_for_audit(principal_id),
            host=host,
            client=client,
            user=principal_id,
            tool=tool,
            outcome=outcome,
            server_name=server,
            ip_address=host,
        )
