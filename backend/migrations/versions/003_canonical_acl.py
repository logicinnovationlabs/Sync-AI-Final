"""Add Block C canonical document / identity / ACL tables.

Revision ID: 003_canonical_acl
Revises: 002_block_n_admin
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_canonical_acl"
down_revision = "002_block_n_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())

    if "canonical_documents" not in existing:
        op.create_table(
            "canonical_documents",
            sa.Column("id", sa.String(512), primary_key=True, nullable=False),
            sa.Column("source_type", sa.String(100), nullable=False),
            sa.Column("source_id", sa.String(512), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("title", sa.String(1024), nullable=False),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("url", sa.Text(), nullable=True),
            sa.Column("mime_type", sa.String(255), nullable=False, server_default=""),
            sa.Column("detected_mime_type", sa.String(255), nullable=False, server_default=""),
            sa.Column("mime_mismatch", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("file_extension", sa.String(64), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
            sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("owner_principal_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("creator_principal_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("last_modifier_principal_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("structured_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("parent_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_canonical_documents_source_type", "canonical_documents", ["source_type"])
        op.create_index("ix_canonical_documents_tenant_id", "canonical_documents", ["tenant_id"])

    if "identity_principals" not in existing:
        op.create_table(
            "identity_principals",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("source_identities", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "email", name="uq_identity_principals_tenant_email"),
        )
        op.create_index("ix_identity_principals_tenant_id", "identity_principals", ["tenant_id"])
        op.create_index("ix_identity_principals_email", "identity_principals", ["email"])

    if "identity_groups" not in existing:
        op.create_table(
            "identity_groups",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("source_type", sa.String(100), nullable=False),
            sa.Column("source_id", sa.String(512), nullable=False),
            sa.Column("member_principal_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
            sa.Column("member_group_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("source_type", "source_id", "tenant_id", name="uq_identity_groups_source"),
        )
        op.create_index("ix_identity_groups_tenant_id", "identity_groups", ["tenant_id"])
        op.create_index("ix_identity_groups_email", "identity_groups", ["email"])

    if "acl_entries" not in existing:
        op.create_table(
            "acl_entries",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("document_id", sa.String(512), nullable=False),
            sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("permission", sa.String(32), nullable=False),
            sa.Column("granted_via", sa.String(64), nullable=False),
            sa.Column("source_container_id", sa.String(512), nullable=True),
            sa.Column("is_deny", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("source_type", sa.String(100), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_acl_entries_document_id", "acl_entries", ["document_id"])
        op.create_index("ix_acl_entries_tenant_id", "acl_entries", ["tenant_id"])

    if "container_acl_entries" not in existing:
        op.create_table(
            "container_acl_entries",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("container_id", sa.String(512), nullable=False),
            sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("permission", sa.String(32), nullable=False),
            sa.Column("is_deny", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("source_type", sa.String(100), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_container_acl_entries_container_id", "container_acl_entries", ["container_id"])
        op.create_index("ix_container_acl_entries_tenant_id", "container_acl_entries", ["tenant_id"])

    if "container_edges" not in existing:
        op.create_table(
            "container_edges",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("parent_container_id", sa.String(512), nullable=False),
            sa.Column("child_container_id", sa.String(512), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source_type", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("child_container_id", "tenant_id", name="uq_container_edges_child_tenant"),
        )
        op.create_index("ix_container_edges_child_container_id", "container_edges", ["child_container_id"])
        op.create_index("ix_container_edges_tenant_id", "container_edges", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("container_edges")
    op.drop_table("container_acl_entries")
    op.drop_table("acl_entries")
    op.drop_table("identity_groups")
    op.drop_table("identity_principals")
    op.drop_table("canonical_documents")
