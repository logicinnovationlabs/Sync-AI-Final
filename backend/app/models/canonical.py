"""SQLAlchemy models for Block C canonical documents, identities, and ACLs.

These live in the per-tenant database. Table names are prefixed so they do not
collide with SCIM ``users`` / ``groups``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class CanonicalDocumentRow(Base, TimestampMixin):
    __tablename__ = "canonical_documents"

    id: Mapped[str] = mapped_column(String(512), primary_key=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    detected_mime_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    mime_mismatch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    file_extension: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    owner_principal_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    creator_principal_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    last_modifier_principal_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    structured_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    parent_ids: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)


class IdentityPrincipalRow(Base, TimestampMixin):
    __tablename__ = "identity_principals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_identity_principals_tenant_email"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_identities: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)


class IdentityGroupRow(Base, TimestampMixin):
    __tablename__ = "identity_groups"
    __table_args__ = (
        UniqueConstraint(
            "source_type", "source_id", "tenant_id", name="uq_identity_groups_source"
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    member_principal_ids: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    member_group_ids: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)


class ACLEntryRow(Base, TimestampMixin):
    __tablename__ = "acl_entries"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    document_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    principal_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    group_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    permission: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_via: Mapped[str] = mapped_column(String(64), nullable=False)
    source_container_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_deny: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)


class ContainerACLEntryRow(Base, TimestampMixin):
    __tablename__ = "container_acl_entries"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    container_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    principal_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    group_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    permission: Mapped[str] = mapped_column(String(32), nullable=False)
    is_deny: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)


class ContainerEdgeRow(Base, TimestampMixin):
    __tablename__ = "container_edges"
    __table_args__ = (
        UniqueConstraint(
            "child_container_id", "tenant_id", name="uq_container_edges_child_tenant"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    parent_container_id: Mapped[str] = mapped_column(String(512), nullable=False)
    child_container_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
