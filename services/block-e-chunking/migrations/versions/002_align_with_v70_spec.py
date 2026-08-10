"""Align schema with Master Build Prompt v7.0 specification

Revision ID: 002
Revises: 001
Create Date: 2026-08-04

[ALIGNMENT - v7.0 §2.1, §2.2]:
- RENAME columns in chunk_records: content_text → chunk_text, source_span_start → start_byte, source_span_end → end_byte
- RENAME column in embedding_jobs: model_version → model_version_target
- Add missing columns to chunk_records: node_type, language, object_store_ref, truncated
- Add missing columns to embedding_jobs: document_id (denormalized)
- Add CHECK constraint for chunk_type (8 values: 6 code + 2 prose)
- Add CHECK constraint for embedding_jobs status (includes 'skipped')
- Add ON UPDATE trigger for updated_at on both tables
- Add required indexes per v7.0 spec

[HARDENING - v7.0 §2.3]:
- DB-level DEFAULT now() already present in 001
- This migration adds ON UPDATE trigger to ensure updated_at changes on every write
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: RENAME columns in chunk_records to match v7.0 §2.1 spec
    op.alter_column('chunk_records', 'content_text', new_column_name='chunk_text')
    op.alter_column('chunk_records', 'source_span_start', new_column_name='start_byte')
    op.alter_column('chunk_records', 'source_span_end', new_column_name='end_byte')
    
    # Step 2: RENAME column in embedding_jobs to match v7.0 §2.2 spec
    op.alter_column('embedding_jobs', 'model_version', new_column_name='model_version_target')
    
    # Step 3: Add new columns to chunk_records (nullable initially for migration safety)
    op.add_column('chunk_records', sa.Column('node_type', sa.String(64), nullable=True))
    op.add_column('chunk_records', sa.Column('language', sa.String(32), nullable=True))
    op.add_column('chunk_records', sa.Column('object_store_ref', sa.Text(), nullable=True))
    op.add_column('chunk_records', sa.Column('truncated', sa.Boolean(), nullable=True, server_default='false'))
    
    # Step 4: Add new columns to embedding_jobs
    op.add_column('embedding_jobs', sa.Column('document_id', sa.String(256), nullable=True))
    
    # Step 3: Create ON UPDATE trigger function for updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    
    # Step 4: Add ON UPDATE triggers for both tables
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
    
    # Step 5: Add CHECK constraint for chunk_type (8 values per v7.0 §2.1)
    op.execute("""
        ALTER TABLE chunk_records
        DROP CONSTRAINT IF EXISTS chunk_records_chunk_type_check;
        
        ALTER TABLE chunk_records
        ADD CONSTRAINT chunk_records_chunk_type_check
        CHECK (chunk_type IN (
            'repo_metadata',
            'file_summary',
            'import_block',
            'function_method',
            'class_module',
            'comment_docstring',
            'prose_paragraph',
            'prose_section'
        ));
    """)
    
    # Step 6: Add CHECK constraint for embedding_jobs status (include 'skipped')
    op.execute("""
        ALTER TABLE embedding_jobs
        DROP CONSTRAINT IF EXISTS embedding_jobs_status_check;
        
        ALTER TABLE embedding_jobs
        ADD CONSTRAINT embedding_jobs_status_check
        CHECK (status IN (
            'pending',
            'in_progress',
            'completed',
            'failed',
            'skipped'
        ));
    """)
    
    # Step 7: Add index for (tenant_id, embedding_model_version) per v7.0 §2.1
    # Note: embedding_vector is LargeBinary, so we index on tenant_id and model_version
    op.create_index(
        'idx_chunk_records_tenant_model_vector',
        'chunk_records',
        ['tenant_id', 'embedding_model_version']
    )
    
    # Step 8: Add index for source_run_id per v7.0 §2.1
    op.create_index('idx_chunk_records_source_run_id', 'chunk_records', ['source_run_id'])
    
    # Step 9: Add index for (document_id, status) in embedding_jobs per v7.0 §2.2
    op.create_index('idx_embedding_jobs_doc_status', 'embedding_jobs', ['document_id', 'status'])
    
    # Step 10: Add index for created_at in embedding_jobs per v7.0 §2.2
    op.create_index('idx_embedding_jobs_created_at', 'embedding_jobs', ['created_at'])


def downgrade():
    # Drop new indexes
    op.drop_index('idx_embedding_jobs_created_at', table_name='embedding_jobs')
    op.drop_index('idx_embedding_jobs_doc_status', table_name='embedding_jobs')
    op.drop_index('idx_chunk_records_source_run_id', table_name='chunk_records')
    op.drop_index('idx_chunk_records_tenant_model_vector', table_name='chunk_records')
    
    # Drop CHECK constraints
    op.execute("""
        ALTER TABLE embedding_jobs
        DROP CONSTRAINT IF EXISTS embedding_jobs_status_check;
    """)
    
    op.execute("""
        ALTER TABLE chunk_records
        DROP CONSTRAINT IF EXISTS chunk_records_chunk_type_check;
    """)
    
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS update_embedding_jobs_updated_at ON embedding_jobs")
    op.execute("DROP TRIGGER IF EXISTS update_chunk_records_updated_at ON chunk_records")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column")
    
    # Drop new columns from embedding_jobs
    op.drop_column('embedding_jobs', 'document_id')
    
    # Drop new columns from chunk_records
    op.drop_column('chunk_records', 'truncated')
    op.drop_column('chunk_records', 'object_store_ref')
    op.drop_column('chunk_records', 'language')
    op.drop_column('chunk_records', 'node_type')
    
    # RENAME columns back to original names
    op.alter_column('chunk_records', 'chunk_text', new_column_name='content_text')
    op.alter_column('chunk_records', 'start_byte', new_column_name='source_span_start')
    op.alter_column('chunk_records', 'end_byte', new_column_name='source_span_end')
    op.alter_column('embedding_jobs', 'model_version_target', new_column_name='model_version')
