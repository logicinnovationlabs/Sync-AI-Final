"""
Chunk models for Block E: Chunking & Embeddings
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, JSON, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ChunkRecord(Base, TimestampMixin):
    """
    Chunk record model for storing document chunks and embeddings.
    
    Each chunk represents a portion of a document that has been
    split for embedding and search purposes.
    """
    __tablename__ = "chunk_records"
    
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_vector: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    
    embedding_model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    chunk_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index('idx_chunk_tenant_document', 'tenant_id', 'document_id'),
        Index('idx_chunk_tenant_model', 'tenant_id', 'embedding_model_version'),
    )
