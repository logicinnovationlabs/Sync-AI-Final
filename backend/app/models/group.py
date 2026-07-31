"""
Group and GroupMembership models - per-tenant database.
"""

from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Group(Base, TimestampMixin):
    """
    Group model (per-tenant database).
    
    sync_version is incremented only when membership actually changes.
    """

    __tablename__ = "groups"

    group_id: Mapped[UUID] = mapped_column(
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
    group_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="e.g., 'security', 'distribution', 'role'",
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_group_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="External group identifier from source system",
    )
    sync_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Incremented only when membership changes",
    )
    last_membership_update: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Group(id={self.group_id}, name={self.display_name})>"


class GroupMembership(Base, TimestampMixin):
    """
    Group membership association table (per-tenant database).
    """

    __tablename__ = "group_memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "principal_id", name="uq_group_principal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    principal_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.principal_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<GroupMembership(group={self.group_id}, user={self.principal_id})>"
