"""
Application configuration using Pydantic Settings.
All environment variables are loaded here.
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# When SNYQ_IGNORE_ENV_FILE=1, do not open .env (verification / CI).
_ENV_FILE = None if os.getenv("SNYQ_IGNORE_ENV_FILE") == "1" else ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Control-plane database (stores tenant routing metadata)
    control_plane_database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/control_plane"
    )

    # Cloud Supabase Postgres (direct DB URL). Prefer this for Phase 0 §1.2 (a).
    # Never log or print this value — presence + successful query only.
    supabase_db_url: Optional[str] = Field(default=None)

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
    # Structural key-rotation support (§14.4): active key id embedded as JWT kid
    jwt_active_kid: str = Field(default="key-2026-08")

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

    # Block C: text extraction / OCR
    tesseract_path: str = Field(default="/usr/bin/tesseract")
    ocr_language: str = Field(default="eng")
    ocr_timeout_seconds: int = Field(default=30)
    max_extracted_chars: int = Field(default=500000)

    # Block C: identity / ACL caches
    identity_cache_ttl: int = Field(default=86400)
    acl_inheritance_cache_ttl: int = Field(default=600)
    acl_revalidation_interval_seconds: int = Field(default=900)


# Global settings instance
settings = Settings()
