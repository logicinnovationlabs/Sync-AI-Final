"""
Application configuration using Pydantic Settings.

Single source of truth: environment variables (backend/.env for local/dev).
Required platform variables fail loudly when missing/empty — no secret defaults.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, model_validator
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
        populate_by_name=True,
    )

    # ------------------------------------------------------------------
    # Tenancy & Identity (Block A) — master-prompt names
    # ------------------------------------------------------------------
    tenant_metadata_service_url: str = Field(
        ...,
        validation_alias=AliasChoices(
            "TENANT_METADATA_SERVICE_URL", "tenant_metadata_service_url"
        ),
    )
    oauth_issuer_url: str = Field(
        ...,
        validation_alias=AliasChoices(
            "OAUTH_ISSUER_URL", "OIDC_ISSUER", "oauth_issuer_url"
        ),
    )
    scim_sync_endpoint: str = Field(
        ...,
        validation_alias=AliasChoices(
            "SCIM_SYNC_ENDPOINT", "SCIM_ENDPOINT", "scim_sync_endpoint"
        ),
    )
    jwt_private_key_path: str = Field(
        ...,
        validation_alias=AliasChoices("JWT_PRIVATE_KEY_PATH", "jwt_private_key_path"),
    )
    jwt_public_key_path: str = Field(
        ...,
        validation_alias=AliasChoices("JWT_PUBLIC_KEY_PATH", "jwt_public_key_path"),
    )
    session_store_redis_url: str = Field(
        ...,
        validation_alias=AliasChoices(
            "SESSION_STORE_REDIS_URL", "REDIS_URL", "session_store_redis_url"
        ),
    )

    # ------------------------------------------------------------------
    # Storage substrate (Block D)
    # ------------------------------------------------------------------
    db_host: str = Field(..., validation_alias=AliasChoices("DB_HOST", "db_host"))
    db_name: str = Field(..., validation_alias=AliasChoices("DB_NAME", "db_name"))
    db_user: str = Field(..., validation_alias=AliasChoices("DB_USER", "db_user"))
    db_password: str = Field(
        ..., validation_alias=AliasChoices("DB_PASSWORD", "db_password")
    )
    object_store_connection_string: str = Field(
        ...,
        validation_alias=AliasChoices(
            "OBJECT_STORE_CONNECTION_STRING", "object_store_connection_string"
        ),
    )
    kms_key_vault_url: str = Field(
        ...,
        validation_alias=AliasChoices("KMS_KEY_VAULT_URL", "kms_key_vault_url"),
    )
    kms_key_name: str = Field(
        ..., validation_alias=AliasChoices("KMS_KEY_NAME", "kms_key_name")
    )

    # ------------------------------------------------------------------
    # Connectors & ingestion (Block B)
    # ------------------------------------------------------------------
    kafka_brokers: str = Field(
        ..., validation_alias=AliasChoices("KAFKA_BROKERS", "kafka_brokers")
    )
    kafka_topic_raw: str = Field(
        ..., validation_alias=AliasChoices("KAFKA_TOPIC_RAW", "kafka_topic_raw")
    )
    kafka_topic_canonical: str = Field(
        ...,
        validation_alias=AliasChoices("KAFKA_TOPIC_CANONICAL", "kafka_topic_canonical"),
    )
    connector_rate_limit_per_source: str = Field(
        ...,
        validation_alias=AliasChoices(
            "CONNECTOR_RATE_LIMIT_PER_SOURCE", "connector_rate_limit_per_source"
        ),
    )
    vault_secret_path: str = Field(
        ...,
        validation_alias=AliasChoices("VAULT_SECRET_PATH", "vault_secret_path"),
    )

    # ------------------------------------------------------------------
    # Search & indexing (Blocks F & G)
    # ------------------------------------------------------------------
    lexical_search_url: str = Field(
        ...,
        validation_alias=AliasChoices("LEXICAL_SEARCH_URL", "lexical_search_url"),
    )
    vector_search_url: str = Field(
        ...,
        validation_alias=AliasChoices(
            "VECTOR_SEARCH_URL", "QDRANT_URL", "vector_search_url"
        ),
    )
    vector_index_name: str = Field(
        ...,
        validation_alias=AliasChoices(
            "VECTOR_INDEX_NAME", "QDRANT_COLLECTION_NAME", "vector_index_name"
        ),
    )

    # ------------------------------------------------------------------
    # LLM & Assistant (Block L)
    # ------------------------------------------------------------------
    llm_provider: str = Field(
        ...,
        validation_alias=AliasChoices(
            "LLM_PROVIDER", "EMBEDDING_PROVIDER", "llm_provider"
        ),
    )
    model_version: str = Field(
        ...,
        validation_alias=AliasChoices(
            "MODEL_VERSION", "EMBEDDING_MODEL", "model_version"
        ),
    )
    azure_openai_endpoint: Optional[str] = Field(default=None)
    azure_openai_deployment: Optional[str] = Field(default=None)
    azure_openai_api_key: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)

    # ------------------------------------------------------------------
    # Observability (Block O)
    # ------------------------------------------------------------------
    otlp_endpoint: str = Field(
        ..., validation_alias=AliasChoices("OTLP_ENDPOINT", "otlp_endpoint")
    )
    log_level: str = Field(
        ..., validation_alias=AliasChoices("LOG_LEVEL", "log_level")
    )
    metrics_namespace: str = Field(
        ...,
        validation_alias=AliasChoices("METRICS_NAMESPACE", "metrics_namespace"),
    )

    # ------------------------------------------------------------------
    # Legacy / existing Block A–C fields (compat aliases where noted)
    # ------------------------------------------------------------------
    control_plane_database_url: Optional[str] = Field(default=None)
    supabase_db_url: Optional[str] = Field(default=None)

    # Azure Key Vault client URL (optional). Distinct from KMS_KEY_VAULT_URL
    # (HashiCorp/local KMS). Leave empty to use MockVaultClient in local/dev.
    vault_url: Optional[str] = Field(default=None)
    vault_tenant_id: Optional[str] = Field(default=None)
    vault_client_id: Optional[str] = Field(default=None)
    vault_client_secret: Optional[str] = Field(default=None)

    jwt_algorithm: str = Field(default="RS256")
    jwt_issuer: str = Field(default="snyq-platform")
    jwt_active_kid: str = Field(default="key-2026-08")

    token_ttl_access: int = Field(default=3600)
    token_ttl_refresh: int = Field(default=604800)
    tenant_cache_ttl_seconds: int = Field(default=1800)

    oidc_client_id: Optional[str] = Field(default=None)
    oidc_client_secret: Optional[str] = Field(default=None)
    oidc_redirect_uri: Optional[str] = Field(default=None)

    scim_token: Optional[str] = Field(default=None)

    google_client_id: Optional[str] = Field(default=None)
    google_client_secret: Optional[str] = Field(default=None)
    google_redirect_uri: Optional[str] = Field(default=None)
    # Optional env-seeded refresh token for local/real-source verification (7-day Testing apps).
    # Production path still expects tokens in TokenStore after OAuth exchange.
    google_refresh_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_REFRESH_TOKEN", "google_refresh_token"),
    )

    qdrant_api_key: Optional[str] = Field(default=None)
    gemini_api_key: Optional[str] = Field(default=None)
    embedding_dimension: int = Field(default=3072)

    # Connector / assistant token crypto + LLM providers (optional until used)
    token_encryption_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TOKEN_ENCRYPTION_KEY", "token_encryption_key"),
    )
    openrouter_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "openrouter_api_key"),
    )
    qwen_model: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("QWEN_MODEL", "qwen_model"),
    )

    environment: str = Field(default="development")

    tesseract_path: str = Field(default="/usr/bin/tesseract")
    ocr_language: str = Field(default="eng")
    ocr_timeout_seconds: int = Field(default=30)
    max_extracted_chars: int = Field(default=500000)

    identity_cache_ttl: int = Field(default=86400)
    acl_inheritance_cache_ttl: int = Field(default=600)
    acl_revalidation_interval_seconds: int = Field(default=900)

    # ------------------------------------------------------------------
    # Derived / compat properties used by existing modules
    # ------------------------------------------------------------------
    @property
    def redis_url(self) -> str:
        return self.session_store_redis_url

    @property
    def qdrant_url(self) -> str:
        return self.vector_search_url

    @property
    def qdrant_collection_name(self) -> str:
        return self.vector_index_name

    @property
    def embedding_provider(self) -> str:
        return self.llm_provider

    @property
    def embedding_model(self) -> str:
        return self.model_version

    @property
    def oidc_issuer(self) -> Optional[str]:
        return self.oauth_issuer_url

    @property
    def scim_endpoint(self) -> Optional[str]:
        return self.scim_sync_endpoint

    @model_validator(mode="after")
    def _assemble_control_plane_url(self) -> "Settings":
        if not self.control_plane_database_url:
            user = quote_plus(self.db_user)
            password = quote_plus(self.db_password)
            self.control_plane_database_url = (
                f"postgresql+asyncpg://{user}:{password}"
                f"@{self.db_host}:5432/{self.db_name}"
            )
        # Normalize empty Azure vault URL → None (MockVaultClient)
        if isinstance(self.vault_url, str) and not self.vault_url.strip():
            self.vault_url = None
        return self

    def __repr__(self) -> str:
        # Never dump secrets
        return (
            f"Settings(environment={self.environment!r}, "
            f"db_host={self.db_host!r}, log_level={self.log_level!r})"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Global settings instance (import-compatible with existing code)
settings = get_settings()