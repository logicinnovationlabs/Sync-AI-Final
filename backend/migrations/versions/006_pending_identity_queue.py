"""Add pending_identity_queue for unmatched Drive share emails.

Revision ID: 006_pending_identity_queue
Revises: 005_merge_heads
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006_pending_identity_queue"
down_revision = "005_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())

    if "pending_identity_queue" not in existing:
        op.create_table(
            "pending_identity_queue",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source_account_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("document_id", sa.String(512), nullable=False),
            sa.Column("shared_email", sa.Text(), nullable=False),
            sa.Column(
                "first_seen_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "resolved_principal_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
            sa.UniqueConstraint(
                "tenant_id",
                "document_id",
                "shared_email",
                name="uq_pending_identity_tenant_doc_email",
            ),
        )
        op.create_index(
            "ix_pending_identity_queue_tenant_email_resolved",
            "pending_identity_queue",
            ["tenant_id", "shared_email", "resolved_at"],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_pending_identity_queue_tenant_email_resolved",
        table_name="pending_identity_queue",
    )
    op.drop_table("pending_identity_queue")
