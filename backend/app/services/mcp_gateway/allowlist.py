"""Read-only tool_policies lookups. Block N is the only writer."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool_policy import ToolPolicy


async def is_tool_allowed(
    session: AsyncSession,
    *,
    tenant_id: str,
    server_name: str,
    tool_name: str,
) -> bool:
    """True only when a row exists with allowed=True. Missing row = reject."""
    stmt = (
        select(ToolPolicy.allowed)
        .where(ToolPolicy.tenant_id == tenant_id)
        .where(ToolPolicy.server_name == server_name)
        .where(ToolPolicy.tool_name == tool_name)
        .limit(1)
    )
    result = await session.execute(stmt)
    value = result.scalar_one_or_none()
    return bool(value)


async def list_allowed_tools(
    session: AsyncSession,
    *,
    tenant_id: str,
    server_name: str,
) -> list[str]:
    stmt = (
        select(ToolPolicy.tool_name)
        .where(ToolPolicy.tenant_id == tenant_id)
        .where(ToolPolicy.server_name == server_name)
        .where(ToolPolicy.allowed.is_(True))
        .order_by(ToolPolicy.tool_name)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]
