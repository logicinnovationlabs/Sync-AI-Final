"""Add password_hash column to users table

Revision ID: 001_add_password_hash
Revises: 
Create Date: 2026-07-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_password_hash'
down_revision = '000_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add composite email+tenant_id unique index (password_hash already in initial schema)."""
    # password_hash column already created in 000_initial_schema.
    # This migration adds the composite uniqueness index for email within a tenant.
    op.create_index(
        'ix_users_email_unique',
        'users',
        ['email', 'tenant_id'],
        unique=True,
    )


def downgrade() -> None:
    """Remove composite email+tenant_id index."""
    op.drop_index('ix_users_email_unique', table_name='users')
