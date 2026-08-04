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
        sa.Column('chunk_id', sa.String(64), primary_key=True),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('document_id', sa.String(256), nullable=False),
        sa.Column('document_version', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('chunker_version', sa.String(32), nullable=False),
        sa.Column('chunk_type', sa.String(32), nullable=False),
        sa.Column('node_type', sa.String(64), nullable=True),
        sa.Column('language', sa.String(32), nullable=True),
        sa.Column('start_byte', sa.Integer(), nullable=False),
        sa.Column('end_byte', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('object_store_ref', sa.Text(), nullable=True),
        sa.Column('source_run_id', sa.String(64), nullable=False),
        sa.Column('embedding_vector', sa.LargeBinary(), nullable=True),
        sa.Column('embedding_model_version', sa.String(64), nullable=True),
        sa.Column('embedding_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('truncated', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('chunk_content_checksum', sa.String(64), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        # DB-level DEFAULT now() per v7.0 §2.3 [HARDENING]
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    
    # Create indexes
    op.create_index('idx_tenant_document', 'chunk_records', ['tenant_id', 'document_id'])
    op.create_index('idx_embedding_version', 'chunk_records', ['embedding_model_version'])
    op.create_index('idx_deleted_at', 'chunk_records', ['deleted_at'])
    op.create_index('idx_source_run_id', 'chunk_records', ['source_run_id'])
    
    # Create unique constraint per v7.0 §2.3
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
        sa.Column('document_id', sa.String(256), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('model_version_target', sa.String(64), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        # DB-level DEFAULT now() per v7.0 §2.3 [HARDENING]
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    
    # Create indexes
    op.create_index('idx_tenant_status', 'embedding_jobs', ['tenant_id', 'status'])
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_embedding_jobs_chunk_id',
        'embedding_jobs', 'chunk_records',
        ['chunk_id'], ['chunk_id']
    )
    
    # Create ON UPDATE trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    
    # Add ON UPDATE triggers for both tables
    op.execute("""
        CREATE TRIGGER update_chunk_records_updated_at
            BEFORE UPDATE ON chunk_records
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        CREATE TRIGGER update_embedding_jobs_updated_at
            BEFORE UPDATE ON embedding_jobs
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade():
    op.drop_constraint('fk_embedding_jobs_chunk_id', 'embedding_jobs', type_='foreignkey')
    op.drop_index('idx_tenant_status', table_name='embedding_jobs')
    op.drop_table('embedding_jobs')
    
    op.drop_constraint('uq_chunk_natural_key', 'chunk_records', type_='unique')
    op.drop_index('idx_source_run_id', table_name='chunk_records')
    op.drop_index('idx_deleted_at', table_name='chunk_records')
    op.drop_index('idx_embedding_version', table_name='chunk_records')
    op.drop_index('idx_tenant_document', table_name='chunk_records')
    op.drop_table('chunk_records')
    
    # Drop triggers and function
    op.execute("DROP TRIGGER IF EXISTS update_embedding_jobs_updated_at ON embedding_jobs")
    op.execute("DROP TRIGGER IF EXISTS update_chunk_records_updated_at ON chunk_records")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column")
