"""Application configuration for Block G Vector Search Service."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings (env-overridable)."""

    # Vector DB
    vector_db_type: str = "mock"  # "mock" | "qdrant"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: Optional[str] = None
    qdrant_prefer_grpc: bool = False
    embedding_dimensions: int = 64
    collection_prefix: str = "tenant"

    # Optional metadata / pgvector
    database_url: Optional[str] = None

    # Redis ACL cache
    redis_url: str = "redis://localhost:6379/3"
    acl_cache_ttl: int = 600

    # Search defaults
    default_top_k: int = 100
    search_timeout_seconds: float = 0.100
    max_top_k: int = 500

    # Auth
    environment: str = "test"
    jwt_private_key_path: Optional[str] = None
    jwt_public_key_path: Optional[str] = None
    enforce_tenant_isolation: bool = True

    # Observability
    emit_search_events: bool = False

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
