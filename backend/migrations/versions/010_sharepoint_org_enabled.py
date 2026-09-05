"""Add sharepoint_org_enabled on tenants for the admin Enable toggle.

Revision ID: 010_sharepoint_org_enabled
Revises: 009_admin_access_overrides
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa

revision = "010_sharepoint_org_enabled"
down_revision = "009_admin_access_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    if "tenants" not in existing_tables:
        return
    columns = {c["name"] for c in inspector.get_columns("tenants")}
    if "sharepoint_org_enabled" in columns:
        return
    op.add_column(
        "tenants",
        sa.Column(
            "sharepoint_org_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Admin toggle for organization SharePoint connector availability",
        ),
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    if "tenants" not in existing_tables:
        return
    columns = {c["name"] for c in inspector.get_columns("tenants")}
    if "sharepoint_org_enabled" in columns:
        op.drop_column("tenants", "sharepoint_org_enabled")
