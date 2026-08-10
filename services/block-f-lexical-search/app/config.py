"""Application configuration for Block F Lexical Search Service."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings (env-overridable)."""

    # Search backend: "mock" (in-memory BM25) | "opensearch"
    search_backend: str = "mock"
    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    opensearch_user: Optional[str] = None
    opensearch_password: Optional[str] = None
    opensearch_use_ssl: bool = False
    opensearch_verify_certs: bool = False
    index_prefix: str = "lexical"
    refresh_interval: str = "1s"

    # Redis (optional ACL cache)
    redis_url: str = "redis://localhost:6379/4"
    acl_cache_ttl: int = 600

    # Search defaults
    default_size: int = 20
    max_size: int = 100
    search_timeout_seconds: float = 5.0
    snippet_max_chars: int = 240

    # Auth
    environment: str = "test"
    jwt_private_key_path: Optional[str] = None
    jwt_public_key_path: Optional[str] = None
    enforce_tenant_isolation: bool = True

    # Observability
    emit_search_events: bool = False
    service_port: int = 8086

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
