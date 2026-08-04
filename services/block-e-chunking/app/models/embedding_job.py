"""
Embedding job model
"""

from enum import Enum
from sqlalchemy import Column, String, Integer, DateTime, Text, Index, text
from .chunk_record import Base


class JobStatus(str, Enum):
    """Embedding job status per v7.0 §2.2 (includes 'skipped' as first-class terminal state)"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EmbeddingJob(Base):
    """
    embedding_jobs table schema
    Tracks embedding generation jobs
    Per Master Build Prompt v1.0, §4
    """
    __tablename__ = "embedding_jobs"

    job_id = Column(String(64), primary_key=True)  # Application-level id per v7.0 §2.2
    celery_task_id = Column(String(64), nullable=True)  # Celery's id, NEVER the same field per v7.0 §2.2
    tenant_id = Column(String(64), nullable=False)
    chunk_id = Column(String(64), nullable=False)  # FK → chunk_records.id
    document_id = Column(String(256), nullable=True)  # Denormalized for query convenience per v7.0 §2.2
    status = Column(String(16), nullable=False, server_default='pending')
    model_version_target = Column(String(64), nullable=False)  # Target embedding model version
    attempt_count = Column(Integer, nullable=False, server_default='0')
    last_error = Column(Text, nullable=True)
    # DB-level DEFAULT now() per v7.0 §2.3 [HARDENING]
    # ON UPDATE trigger ensures this updates on every write
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))

    __table_args__ = (
        Index('idx_tenant_status', 'tenant_id', 'status'),
    )
