"""
Application configuration
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application configuration settings."""
    
    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/block_e"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    
    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_canonical: str = "ingest.canonical.v1"
    kafka_topic_chunks: str = "ingest.chunks.v1"
    kafka_topic_deletions: str = "ingest.chunks.deletions.v1"
    
    # Embedding
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_model_version: str = "v1"
    embedding_dimensions: int = 1536
    embedding_max_tokens: int = 8191
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    
    # Chunking
    chunker_version: str = "1.0.0"
    prose_max_tokens: int = 512
    prose_overlap_tokens: int = 50
    
    # Tenant Isolation
    enforce_tenant_isolation: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
