"""Merge parallel Alembic heads.

003_canonical_acl and 004_tenant_id_varchar both revise 002_block_n_admin
(004 via 003_tool_policies). `alembic upgrade head` refused to boot the API.

Revision ID: 005_merge_heads
Revises: 004_tenant_id_varchar, 003_canonical_acl
Create Date: 2026-08-20
"""

revision = "005_merge_heads"
down_revision = ("004_tenant_id_varchar", "003_canonical_acl")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
