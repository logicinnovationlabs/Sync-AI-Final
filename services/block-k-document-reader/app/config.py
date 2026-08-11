"""Application configuration for Block K Document Reader Service."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings (env-overridable)."""

    # Auth (Block A)
    environment: str = "test"
    jwt_public_key_path: Optional[str] = None
    jwt_issuer: str = "snyq-platform"
    jwt_algorithm: str = "RS256"
    enforce_tenant_isolation: bool = True

    # Storage backend: "mock" (Phase 1) | "minio" (Phase 2 / Block D)
    storage_backend: str = "mock"
    storage_endpoint: str = "localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "documents"
    storage_secure: bool = False
    db_url: str = "postgresql://user:pass@localhost:5432/block_d"

    # ACL (Block C): "mock" | "http"
    acl_backend: str = "mock"
    acl_service_url: str = "http://localhost:8001"

    # Document size threshold for streaming (bytes)
    stream_threshold_bytes: int = 10 * 1024 * 1024  # 10MB
    stream_chunk_bytes: int = 8192

    # Service
    service_name: str = "block-k-document-reader"
    service_port: int = 8091

    # Fixtures (Phase 1)
    fixtures_path: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
