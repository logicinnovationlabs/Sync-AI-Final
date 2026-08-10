"""Application configuration for Block J Query Federator."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings (all external URLs/toggles env-overridable)."""

    # Service
    service_name: str = "block-j-query-federator"
    service_port: int = 8089
    environment: str = "test"

    # Backend URLs (Blocks F / G / H)
    lexical_search_url: str = "http://localhost:8086"
    vector_search_url: str = "http://localhost:8087"
    graph_service_url: str = "http://localhost:8088"

    # Timeouts / retries (seconds)
    backend_timeout_seconds: float = 0.400
    backend_connect_timeout_seconds: float = 0.100
    backend_max_retries: int = 1
    http_pool_max_connections: int = 100
    http_pool_max_keepalive: int = 20

    # Embedding for vector fan-out
    # mock = deterministic local embedder; openai = remote API
    embedding_backend: str = "mock"
    embedding_dimensions: int = 64
    embedding_model_version: str = "text-embedding-3-large"
    embedding_api_url: Optional[str] = None
    embedding_api_key: Optional[str] = None

    # Ranking
    lexical_weight: float = 0.40
    vector_weight: float = 0.40
    graph_weight: float = 0.20
    rerank_top_k: int = 100
    # mock = lightweight overlap scorer; cross_encoder = sentence-transformers
    reranker_backend: str = "mock"
    reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    reranker_enabled: bool = True
    fusion_only: bool = False  # skip stage-2 when True

    # ACL post-check
    # memory = in-process store (tests/dev); postgres = acl_entries table
    acl_backend: str = "memory"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/block_j"
    acl_batch_size: int = 500

    # Auth (Block A)
    jwt_public_key_path: Optional[str] = None
    jwt_private_key_path: Optional[str] = None
    enforce_tenant_isolation: bool = True

    # Search defaults
    default_page_size: int = 20
    max_page_size: int = 100
    default_candidate_size: int = 50  # per-backend fan-out size

    # Feature flags / graceful degradation
    enable_lexical: bool = True
    enable_vector: bool = True
    enable_graph: bool = True

    # Observability
    enable_prometheus_metrics: bool = True
    log_level: str = "INFO"

    # Fixtures (Block Z path override)
    fixtures_path: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
