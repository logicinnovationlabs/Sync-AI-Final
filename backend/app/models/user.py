"""
User model - lives in each tenant's OWN database.

principal_id is deterministic via UUIDv5(NAMESPACE, idp_subject) for SCIM idempotency (A3).
Supports both SSO (via idp_subject) and native email/password authentication.
"""

from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """
    User/principal model (per-tenant database).
    
    principal_id is generated deterministically via uuid5(NAMESPACE, idp_subject)
    to ensure SCIM sync idempotency.
    
    Supports two authentication modes:
    1. SSO (OIDC): idp_subject is populated, password_hash is NULL
    2. Native: password_hash is populated, idp_subject may be synthetic
    """

    __tablename__ = "users"

    principal_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        comment="Deterministic UUID via uuid5(NAMESPACE, idp_subject) for SCIM idempotency",
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    idp_subject: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="IdP subject (source of truth for principal_id generation, or synthetic for native users)",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        unique=True,
        comment="User email (must be unique within tenant)",
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="bcrypt-hashed password for native auth users (NULL for SSO-only users)",
    )
    source_profiles: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Merged identity profiles from multiple sources",
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )

    def __repr__(self) -> str:
        return f"<User(principal_id={self.principal_id}, email={self.email})>"
