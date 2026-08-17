"""Add Block N admin columns and tables.

Revision ID: 002_block_n_admin
Revises: 001_add_password_hash
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_block_n_admin"
down_revision = "001_add_password_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {c["name"] for c in inspector.get_columns("users")}
    existing_tables = set(inspector.get_table_names())

    if "role" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        )
    if "invited_by" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if "must_change_password" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )
    if "is_active" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        )
    if "token_version" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("users")}
    if "ix_users_is_active" not in existing_indexes:
        op.create_index("ix_users_is_active", "users", ["is_active"])

    if "tenant_connectors" not in existing_tables:
        op.create_table(
            "tenant_connectors",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source_type", sa.String(100), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("setup_by", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("credential_ref", sa.String(255), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint("tenant_id", "source_type", name="uq_tenant_connectors_source"),
        )
        op.create_index("ix_tenant_connectors_tenant_id", "tenant_connectors", ["tenant_id"])

    if "audit_logs" not in existing_tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("action_type", sa.String(100), nullable=False),
            sa.Column("target_json", postgresql.JSONB(), nullable=True),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
        op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
        op.create_index("ix_audit_logs_action_type", "audit_logs", ["action_type"])
        op.create_index(
            "ix_audit_logs_tenant_id_created_at",
            "audit_logs",
            ["tenant_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_tenant_id_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_tenant_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_tenant_connectors_tenant_id", table_name="tenant_connectors")
    op.drop_table("tenant_connectors")

    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_column("users", "token_version")
    op.drop_column("users", "is_active")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "invited_by")
    op.drop_column("users", "role")
