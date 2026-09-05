"""Add admin_access_overrides table for per-document access control.

Revision ID: 009_admin_access_overrides
Revises: 008_rbac_expansion_owner_viewer
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "009_admin_access_overrides"
down_revision = "008_rbac_expansion_owner_viewer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create admin_access_overrides table
    op.create_table(
        "admin_access_overrides",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            index=True,
            comment="Tenant ID - enforces tenant boundary",
        ),
        sa.Column(
            "document_id",
            sa.String(512),
            nullable=False,
            index=True,
            comment="Document ID from canonical_documents table",
        ),
        sa.Column(
            "target_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            index=True,
            comment="Principal ID of the member this override applies to",
        ),
        sa.Column(
            "access",
            sa.Enum("allow", "deny", name="admin_access_type"),
            nullable=False,
            comment="Access type: allow or deny",
        ),
        sa.Column(
            "set_by_admin_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Principal ID of the admin who set this override (audit trail)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        comment="Admin access overrides for per-document access control",
    )

    # Add unique constraint to prevent duplicate overrides for same (document, user) pair
    op.create_unique_constraint(
        "uq_admin_access_overrides_document_user",
        "admin_access_overrides",
        ["document_id", "target_user_id"],
    )

    # Add index for efficient lookup of overrides by tenant
    op.create_index(
        "ix_admin_access_overrides_tenant_document",
        "admin_access_overrides",
        ["tenant_id", "document_id"],
    )


def downgrade() -> None:
    # Drop table
    op.drop_table("admin_access_overrides")
    
    # Drop enum type
    op.execute("DROP TYPE IF EXISTS admin_access_type")
