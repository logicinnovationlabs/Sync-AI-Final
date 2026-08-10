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
    embedding_provider: str = "mock"
    embedding_model: str = "gemini-embedding-001"
    embedding_model_version: str = "v1"
    embedding_dimensions: int = 768
    embedding_max_tokens: int = 8191
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    jwt_public_key_path: Optional[str] = None
    jwt_issuer: str = "snyq-platform"
    jwt_algorithm: str = "RS256"
    block_a_token_validate_url: Optional[str] = None
    fixtures_path: Optional[str] = None
    
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
