"""
Chunk record model
"""

from enum import Enum
from sqlalchemy import Column, String, Integer, DateTime, Text, LargeBinary, Index, text, Boolean
from sqlalchemy.ext.declarative import declarative_base

# Shared base for all models
Base = declarative_base()


class ChunkType(str, Enum):
    """Eight chunk types per v7.0 §2.1 (6 code + 2 prose)"""
    REPO_METADATA = "repo_metadata"
    FILE_SUMMARY = "file_summary"
    IMPORT_BLOCK = "import_block"
    FUNCTION_METHOD = "function_method"
    CLASS_MODULE = "class_module"
    COMMENT_DOCSTRING = "comment_docstring"
    PROSE_PARAGRAPH = "prose_paragraph"
    PROSE_SECTION = "prose_section"


class ChunkRecord(Base):
    """
    chunk_records table schema
    Stores chunked content with embeddings
    Per Master Build Prompt v1.0, §4
    """
    __tablename__ = "chunk_records"

    # Per v7.0 §2.1: UUID PK with server_default=gen_random_uuid()
    chunk_id = Column(String(64), primary_key=True)  # TODO: Migrate to UUID type in future migration
    tenant_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(256), nullable=False)
    document_version = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunker_version = Column(String(32), nullable=False)
    chunk_type = Column(String(32), nullable=False)
    node_type = Column(String(64), nullable=True)  # AST node type for code chunks, NULL for prose
    language = Column(String(32), nullable=True)  # NULL for prose
    start_byte = Column(Integer, nullable=False)  # Byte offset into canonical document's extracted_text
    end_byte = Column(Integer, nullable=False)  # Byte offset into canonical document's extracted_text
    token_count = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)  # Inline for chunks under 8KB
    object_store_ref = Column(Text, nullable=True)  # Populated when chunk_text exceeds inline threshold
    source_run_id = Column(String(64), nullable=False)
    embedding_vector = Column(LargeBinary, nullable=True)  # NULL until embedded
    embedding_model_version = Column(String(64), nullable=True)  # NULL until embedded
    embedding_timestamp = Column(DateTime(timezone=True), nullable=True)
    truncated = Column(Boolean, nullable=True, server_default='false')  # Flag for chunks exceeding ceiling
    content_hash = Column(String(64), nullable=False)  # SHA256 of content
    chunk_content_checksum = Column(String(64), nullable=False)  # sha256 of normalized chunk text for idempotency
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # For tombstone handling
    # DB-level DEFAULT now() per v7.0 §2.3 [HARDENING]
    # ON UPDATE trigger ensures this updates on every write
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))

    __table_args__ = (
        Index('idx_tenant_document', 'tenant_id', 'document_id'),
        Index('idx_embedding_version', 'embedding_model_version'),
        Index('idx_deleted_at', 'deleted_at'),
        Index('idx_source_run_id', 'source_run_id'),
        # Unique constraint per v7.0 §2.3
        Index('uq_chunk_natural_key', 'tenant_id', 'document_id', 'document_version', 'chunk_index', 'chunker_version', unique=True),
    )
