"""Initial schema - create all tables

Revision ID: 000_initial_schema
Revises: 
Create Date: 2026-07-30

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '000_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tenants',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('subdomain', sa.String(255), nullable=False, unique=True),
        sa.Column('tenancy_mode', sa.String(50), nullable=False, server_default='isolated_db'),
        sa.Column('config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('db_host', sa.String(255), nullable=False),
        sa.Column('db_name', sa.String(255), nullable=False),
        sa.Column('db_user', sa.String(255), nullable=False),
        sa.Column('db_secret_key', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_tenants_subdomain', 'tenants', ['subdomain'], unique=True)

    op.create_table(
        'users',
        sa.Column('principal_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('idp_subject', sa.String(255), nullable=False, unique=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('source_profiles', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'])
    op.create_index('ix_users_idp_subject', 'users', ['idp_subject'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_status', 'users', ['status'])

    op.create_table(
        'groups',
        sa.Column('group_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_type', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('source_group_key', sa.String(255), nullable=False),
        sa.Column('sync_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_membership_update', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_groups_tenant_id', 'groups', ['tenant_id'])
    op.create_index('ix_groups_source_group_key', 'groups', ['source_group_key'])

    op.create_table(
        'group_memberships',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('groups.group_id', ondelete='CASCADE'), nullable=False),
        sa.Column('principal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.principal_id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('group_id', 'principal_id', name='uq_group_principal'),
    )
    op.create_index('ix_group_memberships_group_id', 'group_memberships', ['group_id'])
    op.create_index('ix_group_memberships_principal_id', 'group_memberships', ['principal_id'])
    op.create_index('ix_group_memberships_tenant_id', 'group_memberships', ['tenant_id'])

    op.create_table(
        'oauth_clients',
        sa.Column('client_id', sa.String(255), primary_key=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('hashed_secret', sa.String(255), nullable=False),
        sa.Column('client_type', sa.String(50), nullable=False),
        sa.Column('redirect_uris', postgresql.ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_oauth_clients_tenant_id', 'oauth_clients', ['tenant_id'])

    op.create_table(
        'refresh_tokens',
        sa.Column('token_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('principal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.principal_id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('hashed_token', sa.String(255), nullable=False, unique=True),
        sa.Column('revoked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_refresh_tokens_principal_id', 'refresh_tokens', ['principal_id'])
    op.create_index('ix_refresh_tokens_tenant_id', 'refresh_tokens', ['tenant_id'])
    op.create_index('ix_refresh_tokens_revoked', 'refresh_tokens', ['revoked'])
    op.create_index('ix_refresh_tokens_expires_at', 'refresh_tokens', ['expires_at'])

    op.create_table(
        'scope_registry',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scope_name', sa.String(255), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_scope_registry_tenant_id', 'scope_registry', ['tenant_id'])
    op.create_index('ix_scope_registry_scope_name', 'scope_registry', ['scope_name'], unique=True)

    op.create_table(
        'sync_cursors',
        sa.Column('tenant_id', sa.String(255), primary_key=True, nullable=False),
        sa.Column('source_type', sa.String(100), primary_key=True, nullable=False),
        sa.Column('cursor', sa.String(500), nullable=True),
        sa.Column('watch_data', postgresql.JSONB(), nullable=True),
        sa.Column('watch_expiration', sa.BigInteger(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_sync_cursors_tenant_id', 'sync_cursors', ['tenant_id'])
    op.create_index('ix_sync_cursors_source_type', 'sync_cursors', ['source_type'])
    op.create_index('ix_sync_cursors_expiration', 'sync_cursors', ['watch_expiration'])


def downgrade() -> None:
    op.drop_table('sync_cursors')
    op.drop_table('scope_registry')
    op.drop_table('refresh_tokens')
    op.drop_table('oauth_clients')
    op.drop_table('group_memberships')
    op.drop_table('groups')
    op.drop_table('users')
    op.drop_table('tenants')

