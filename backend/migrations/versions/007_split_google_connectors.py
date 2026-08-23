"""Split Google Workspace into Personal and Organization connectors.

Revision ID: 007_split_google_connectors
Revises: 006_pending_identity_queue
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007_split_google_connectors"
down_revision = "006_pending_identity_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Add connection_scope column to tenant_connectors (nullable initially)
    if "tenant_connectors" in existing_tables:
        op.add_column(
            "tenant_connectors",
            sa.Column(
                "connection_scope",
                sa.String(50),
                nullable=True,
                server_default="personal",
                comment="'personal' for per-user OAuth, 'organization' for admin service account"
            ),
        )

    # Add google_org_workspace_enabled column to tenants
    if "tenants" in existing_tables:
        op.add_column(
            "tenants",
            sa.Column(
                "google_org_workspace_enabled",
                sa.Boolean(),
                nullable=False,
                server_default="false",
                comment="Admin toggle for organization Google Workspace connector availability"
            ),
        )

    # Backfill existing tenant_connectors rows with connection_scope = 'personal'
    if "tenant_connectors" in existing_tables:
        op.execute(
            "UPDATE tenant_connectors SET connection_scope = 'personal' WHERE connection_scope IS NULL"
        )

    # Make connection_scope non-nullable
    if "tenant_connectors" in existing_tables:
        op.alter_column(
            "tenant_connectors",
            "connection_scope",
            nullable=False,
            server_default="personal",
        )

    # Drop old unique constraint and add new one with connection_scope
    if "tenant_connectors" in existing_tables:
        # Check if old constraint exists
        old_constraint_name = "uq_tenant_connectors_source"
        constraints = inspector.get_unique_constraints("tenant_connectors")
        constraint_names = [c.get("name") for c in constraints]
        
        if old_constraint_name in constraint_names:
            op.drop_constraint(old_constraint_name, "tenant_connectors", type_="unique")
        
        # Add new unique constraint
        op.create_unique_constraint(
            "uq_tenant_connectors_source_scope",
            "tenant_connectors",
            ["tenant_id", "source_type", "connection_scope"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Reverse the unique constraint change
    if "tenant_connectors" in existing_tables:
        new_constraint_name = "uq_tenant_connectors_source_scope"
        constraints = inspector.get_unique_constraints("tenant_connectors")
        constraint_names = [c.get("name") for c in constraints]
        
        if new_constraint_name in constraint_names:
            op.drop_constraint(new_constraint_name, "tenant_connectors", type_="unique")
        
        # Restore old unique constraint
        op.create_unique_constraint(
            "uq_tenant_connectors_source",
            "tenant_connectors",
            ["tenant_id", "source_type"],
        )

    # Make connection_scope nullable again
    if "tenant_connectors" in existing_tables:
        op.alter_column(
            "tenant_connectors",
            "connection_scope",
            nullable=True,
        )

    # Drop connection_scope column
    if "tenant_connectors" in existing_tables:
        op.drop_column("tenant_connectors", "connection_scope")

    # Drop google_org_workspace_enabled column
    if "tenants" in existing_tables:
        op.drop_column("tenants", "google_org_workspace_enabled")
