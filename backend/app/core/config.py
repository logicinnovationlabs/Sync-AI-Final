"""
Application configuration using Pydantic Settings.
All environment variables are loaded here.
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Control-plane database (stores tenant routing metadata)
    control_plane_database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/control_plane"
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379")

    # Vault configuration
    vault_url: Optional[str] = Field(default=None)
    vault_tenant_id: Optional[str] = Field(default=None)
    vault_client_id: Optional[str] = Field(default=None)
    vault_client_secret: Optional[str] = Field(default=None)

    # JWT configuration
    jwt_private_key_path: str = Field(default="/app/keys/private.pem")
    jwt_public_key_path: str = Field(default="/app/keys/public.pem")
    jwt_algorithm: str = Field(default="RS256")
    jwt_issuer: str = Field(default="snyq-platform")

    # Token TTLs
    token_ttl_access: int = Field(default=3600)  # 1 hour
    token_ttl_refresh: int = Field(default=604800)  # 7 days

    # Tenant cache TTL
    tenant_cache_ttl_seconds: int = Field(default=1800)  # 30 minutes

    # OIDC/SSO
    oidc_issuer: Optional[str] = Field(default=None)
    oidc_client_id: Optional[str] = Field(default=None)
    oidc_client_secret: Optional[str] = Field(default=None)
    oidc_redirect_uri: str = Field(default="http://localhost:8000/auth/callback")

    # SCIM
    scim_endpoint: Optional[str] = Field(default=None)
    scim_token: Optional[str] = Field(default=None)

    # Google OAuth
    google_client_id: Optional[str] = Field(default=None)
    google_client_secret: Optional[str] = Field(default=None)
    google_redirect_uri: str = Field(default="http://localhost:8000/api/v1/connectors/google/callback")

    # Qdrant
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: Optional[str] = Field(default=None)
    qdrant_collection_name: str = Field(default="documents")

    # Gemini & Embeddings
    gemini_api_key: Optional[str] = Field(default=None)
    embedding_provider: str = Field(default="fake")
    embedding_model: str = Field(default="gemini-embedding-001")
    embedding_dimension: int = Field(default=3072)

    # Environment
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")


# Global settings instance
settings = Settings()
