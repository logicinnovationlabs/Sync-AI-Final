"""MCP persona tool allowlist — control-plane table (Block M read, Block N write)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ToolPolicy(Base, TimestampMixin):
    """Per-tenant, per-persona allow/deny row for one MCP tool.

    Block N is the only writer. Block M is read-only. No service logic here.
    """

    __tablename__ = "tool_policies"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "server_name",
            "tool_name",
            name="uq_tool_policies_tenant_server_tool",
        ),
        Index("ix_tool_policies_tenant_id_server_name", "tenant_id", "server_name"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    server_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="MCP persona endpoint: default, engineering, sales, support, ...",
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<ToolPolicy(tenant_id={self.tenant_id}, server={self.server_name}, "
            f"tool={self.tool_name}, allowed={self.allowed})>"
        )
