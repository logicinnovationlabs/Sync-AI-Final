"""
Scope registry model - per-tenant database.

Defines available scopes for OAuth tokens and access control.
"""

from uuid import UUID
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ScopeRegistry(Base, TimestampMixin):
    """
    Scope registry (per-tenant database).
    
    Defines the available scopes for API access control.
    """

    __tablename__ = "scope_registry"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    scope_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="e.g., 'search.read', 'admin.audit.read'",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ScopeRegistry(scope={self.scope_name})>"
