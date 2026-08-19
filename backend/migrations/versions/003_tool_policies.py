"""Add tool_policies table for MCP persona allowlists.

Revision ID: 003_tool_policies
Revises: 002_block_n_admin
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_tool_policies"
down_revision = "002_block_n_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("server_name", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
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
        sa.UniqueConstraint(
            "tenant_id",
            "server_name",
            "tool_name",
            name="uq_tool_policies_tenant_server_tool",
        ),
    )
    op.create_index("ix_tool_policies_tenant_id", "tool_policies", ["tenant_id"])
    op.create_index(
        "ix_tool_policies_tenant_id_server_name",
        "tool_policies",
        ["tenant_id", "server_name"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tool_policies_tenant_id_server_name", table_name="tool_policies"
    )
    op.drop_index("ix_tool_policies_tenant_id", table_name="tool_policies")
    op.drop_table("tool_policies")
