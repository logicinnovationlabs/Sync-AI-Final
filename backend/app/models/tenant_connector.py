"""Tenant-wide connector configuration (Block N / Glean-style org connectors)."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class TenantConnector(Base, TimestampMixin):
    """
    Org-level connector config for a tenant.

    Credentials (if provided by admin) live in Vault; ``credential_ref`` is
    the Vault key name only. Per-user OAuth is still required to authorize
    a given principal against the source.
    """

    __tablename__ = "tenant_connectors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_type", name="uq_tenant_connectors_source"),
    )

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
    )
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    setup_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        comment="principal_id of the admin who configured this connector",
    )
    credential_ref: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Vault key NAME for connector credentials, never a secret blob",
    )

    def __repr__(self) -> str:
        return (
            f"<TenantConnector(tenant_id={self.tenant_id}, "
            f"source_type={self.source_type}, enabled={self.enabled})>"
        )
