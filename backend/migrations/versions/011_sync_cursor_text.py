"""Widen sync_cursors.cursor so SharePoint Graph delta URLs are not truncated.

Revision ID: 011_sync_cursor_text
Revises: 010_sharepoint_org_enabled
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "011_sync_cursor_text"
down_revision = "010_sharepoint_org_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "sync_cursors" not in set(inspector.get_table_names()):
        return
    op.alter_column(
        "sync_cursors",
        "cursor",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "sync_cursors" not in set(inspector.get_table_names()):
        return
    op.alter_column(
        "sync_cursors",
        "cursor",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=True,
    )
