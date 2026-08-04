"""Initial schema with DB-level defaults per v7.0 §2.3

Revision ID: 001
Revises: 
Create Date: 2026-08-03

[HARDENING - v7.0 §2.3]:
- created_at and updated_at have DB-level DEFAULT now(), not application-level defaults
- This prevents NOT NULL violations during placeholder row inserts
- Every NOT NULL column has either a DB default or must be supplied by every insert path
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create chunk_records table with DB-level defaults
    op.create_table(
        'chunk_records',
        # chunk_id is String(64) to exactly fit SHA256 hex digest (64 characters)
        # This is an intentional exact-fit constraint with zero headroom
        # Future format changes (prefixes, tags, version markers) would require migration
        sa.Column('chunk_id', sa.String(64), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('document_id', sa.String(256), nullable=False),
        sa.Column('document_version', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('chunk_type', sa.String(32), nullable=False),
        sa.Column('content_text', sa.Text(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('source_span_start', sa.Integer(), nullable=False),
        sa.Column('source_span_end', sa.Integer(), nullable=False),
        sa.Column('embedding_vector', sa.LargeBinary(), nullable=True),
        sa.Column('embedding_model_version', sa.String(64), nullable=True),
        sa.Column('embedding_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('chunker_version', sa.String(32), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('chunk_content_checksum', sa.String(64), nullable=False),
        sa.Column('source_run_id', sa.String(64), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        # DB-level DEFAULT now() per v7.0 §2.3 [HARDENING]
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    
    # Create indexes
    op.create_index('idx_chunk_records_tenant', 'chunk_records', ['tenant_id'])
    op.create_index('idx_chunk_records_doc', 'chunk_records', ['tenant_id', 'document_id', 'document_version'])
    op.create_index('idx_chunk_records_model_ver', 'chunk_records', ['tenant_id', 'embedding_model_version'])
    op.create_index('idx_chunk_records_pending', 'chunk_records', ['tenant_id'], 
                     postgresql_where=(sa.text('embedding_vector IS NULL AND deleted_at IS NULL')))
    
    # Create unique constraint
    op.create_unique_constraint(
        'uq_chunk_natural_key',
        'chunk_records',
        ['tenant_id', 'document_id', 'document_version', 'chunk_index', 'chunker_version']
    )
    
    # Create embedding_jobs table with DB-level defaults
    op.create_table(
        'embedding_jobs',
        # job_id and chunk_id are String(64) to exactly fit SHA256 hex digest (64 characters)
        # This is an intentional exact-fit constraint with zero headroom
        # Future format changes (prefixes, tags, version markers) would require migration
        sa.Column('job_id', sa.String(64), primary_key=True),
        sa.Column('celery_task_id', sa.String(64), nullable=True),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('chunk_id', sa.String(64), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('model_version', sa.String(64), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        # DB-level DEFAULT now() per v7.0 §2.3 [HARDENING]
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    
    # Create indexes
    op.create_index('idx_embedding_jobs_tenant_status', 'embedding_jobs', ['tenant_id', 'status'])
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_embedding_jobs_chunk_id',
        'embedding_jobs', 'chunk_records',
        ['chunk_id'], ['chunk_id']
    )


def downgrade():
    op.drop_constraint('fk_embedding_jobs_chunk_id', 'embedding_jobs', type_='foreignkey')
    op.drop_index('idx_embedding_jobs_tenant_status', table_name='embedding_jobs')
    op.drop_table('embedding_jobs')
    
    op.drop_constraint('uq_chunk_natural_key', 'chunk_records', type_='unique')
    op.drop_index('idx_chunk_records_pending', table_name='chunk_records')
    op.drop_index('idx_chunk_records_model_ver', table_name='chunk_records')
    op.drop_index('idx_chunk_records_doc', table_name='chunk_records')
    op.drop_index('idx_chunk_records_tenant', table_name='chunk_records')
    op.drop_table('chunk_records')
