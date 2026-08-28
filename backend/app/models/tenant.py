"""
Tenant model - lives in the CONTROL-PLANE database only.

This table NEVER stores tenant content or secrets directly.
It stores routing metadata (where to find a tenant's data) and Vault key names.

Critical constraint from Vishwas §28.2/§28.6:
The db_secret_key column stores a Vault key NAME (e.g., 'kv/tenantA/db_password'),
NEVER a password, NEVER an encrypted blob. Anyone with read access to this table
must never be able to reconstruct a working credential.
"""

from typing import Dict, Any
from uuid import UUID, uuid4
from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    """
    Tenant routing metadata (control-plane table).
    
    Lives in a small shared 'control_plane' database.
    Does NOT contain tenant data - only routing information.
    """

    __tablename__ = "tenants"

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subdomain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    tenancy_mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="isolated_db",
        comment="Fixed value 'isolated_db' for this build (Tier 2 per Vishwas §28.1)",
    )
    config: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Tenant-specific configuration (never secrets)",
    )

    # Routing metadata - where to find this tenant's data
    db_host: Mapped[str] = mapped_column(String(255), nullable=False)
    db_name: Mapped[str] = mapped_column(String(255), nullable=False)
    db_user: Mapped[str] = mapped_column(String(255), nullable=False)

    # Vault key NAME only - never a password or encrypted value
    db_secret_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment=(
            "Vault key NAME (e.g., 'kv/tenantA/db_password'), NEVER a password or encrypted value. "
            "The actual secret lives only in Vault. This prevents credential theft via metadata access "
            "(Vishwas §28.2/§28.6)."
        ),
    )
    google_org_workspace_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Admin toggle for organization Google Workspace connector availability",
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.tenant_id}, name={self.name}, subdomain={self.subdomain})>"
