"""Admin access override model for per-document allow/deny controls.

This table allows admins to override default ACL behavior for specific users
on specific documents within their tenant.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SQLEnum, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AdminAccessOverride(Base, TimestampMixin):
    """
    Admin access override for per-document access control.
    
    Allows owner/admin roles to:
    - Explicitly deny a member access to a specific document
    - Explicitly allow a member access to a specific document (even if ACL would deny)
    
    Tenant boundary is enforced: overrides cannot cross tenant boundaries.
    """
    __tablename__ = "admin_access_overrides"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Tenant ID - enforces tenant boundary",
    )
    document_id: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        index=True,
        comment="Document ID from canonical_documents table",
    )
    target_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Principal ID of the member this override applies to",
    )
    access: Mapped[str] = mapped_column(
        SQLEnum("allow", "deny", name="admin_access_type"),
        nullable=False,
        comment="Access type: allow or deny",
    )
    set_by_admin_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        comment="Principal ID of the admin who set this override (audit trail)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.utcnow(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )

    def __repr__(self) -> str:
        return (
            f"<AdminAccessOverride(id={self.id}, document_id={self.document_id}, "
            f"target_user_id={self.target_user_id}, access={self.access})>"
        )
