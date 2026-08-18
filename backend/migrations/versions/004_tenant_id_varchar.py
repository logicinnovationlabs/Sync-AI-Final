"""Change tool_policies.tenant_id and audit_logs.tenant_id to VARCHAR(255),
matching Block D's canonical tenants.tenant_id type.

Revision ID: 004_tenant_id_varchar
Revises: 003_tool_policies
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa

revision = "004_tenant_id_varchar"
down_revision = "003_tool_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tool_policies",
        "tenant_id",
        type_=sa.String(255),
        postgresql_using="tenant_id::text",
        existing_nullable=False,
    )
    op.alter_column(
        "audit_logs",
        "tenant_id",
        type_=sa.String(255),
        postgresql_using="tenant_id::text",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "audit_logs",
        "tenant_id",
        type_=sa.dialects.postgresql.UUID(as_uuid=True),
        postgresql_using="tenant_id::uuid",
        existing_nullable=False,
    )
    op.alter_column(
        "tool_policies",
        "tenant_id",
        type_=sa.dialects.postgresql.UUID(as_uuid=True),
        postgresql_using="tenant_id::uuid",
        existing_nullable=False,
    )
