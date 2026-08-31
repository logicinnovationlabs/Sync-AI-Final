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


def _default_acl_backend() -> str:
    env = (os.getenv("ENVIRONMENT") or "development").strip().lower()
    if env in {"test"}:
        return "mock"
    return "postgres"


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
    storage_backend: str = Field(
        default="mock",
        validation_alias=AliasChoices("STORAGE_BACKEND", "storage_backend"),
    )
    vault_backend: str = Field(
        default="mock",
        validation_alias=AliasChoices("VAULT_BACKEND", "vault_backend"),
    )
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
    lexical_backend: str = Field(
        default="mock",
        validation_alias=AliasChoices("LEXICAL_BACKEND", "lexical_backend"),
    )
    vector_backend: str = Field(
        default="mock",
        validation_alias=AliasChoices("VECTOR_BACKEND", "vector_backend"),
    )
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
    embedding_dimensions: int = Field(
        default=3072,
        validation_alias=AliasChoices(
            "EMBEDDING_DIMENSIONS",
            "embedding_dimensions",
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
    supabase_pooler_url: Optional[str] = Field(default=None)

    # Azure Key Vault client URL (optional). Distinct from KMS_KEY_VAULT_URL
    # (HashiCorp/local KMS). Leave empty to use MockVaultClient in local/dev.
    vault_url: Optional[str] = Field(default=None)
    vault_provider: Optional[str] = Field(
        default="azure",
        validation_alias=AliasChoices("VAULT_PROVIDER", "vault_provider"),
    )
    vault_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("VAULT_TOKEN", "vault_token"),
    )
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
    tenant_bootstrap_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "TENANT_BOOTSTRAP_TOKEN", "tenant_bootstrap_token"
        ),
    )

    google_client_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLIENT_ID", "google_client_id"),
    )
    google_client_secret: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLIENT_SECRET", "google_client_secret"),
    )
    google_redirect_uri: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_REDIRECT_URI", "google_redirect_uri"),
    )
    frontend_url: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("FRONTEND_URL", "frontend_url"),
    )
    celery_broker_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("CELERY_BROKER_URL", "celery_broker_url"),
    )
    celery_result_backend: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("CELERY_RESULT_BACKEND", "celery_result_backend"),
    )
    celery_task_always_eager: bool = Field(
        default=False,
        validation_alias=AliasChoices("CELERY_TASK_ALWAYS_EAGER", "celery_task_always_eager"),
    )
    # Optional env-seeded refresh token for local/real-source verification (7-day Testing apps).
    # Production path still expects tokens in TokenStore after OAuth exchange.
    google_refresh_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_REFRESH_TOKEN", "google_refresh_token"),
    )
    google_drive_credential_mode: str = Field(
        default="oauth",
        validation_alias=AliasChoices(
            "GOOGLE_DRIVE_CREDENTIAL_MODE", "google_drive_credential_mode"
        ),
    )
    google_dwd_impersonate_email: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_DWD_IMPERSONATE_EMAIL", "google_dwd_impersonate_email"
        ),
    )
    google_service_account_vault_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_SERVICE_ACCOUNT_VAULT_KEY", "google_service_account_vault_key"
        ),
    )
    drive_acl_poll_seconds: int = Field(
        default=180,
        validation_alias=AliasChoices("DRIVE_ACL_POLL_SECONDS", "drive_acl_poll_seconds"),
    )
    google_pubsub_verification_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_PUBSUB_VERIFICATION_TOKEN", "google_pubsub_verification_token"
        ),
    )
    google_pubsub_project_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_PUBSUB_PROJECT_ID", "google_pubsub_project_id"
        ),
    )
    google_pubsub_topic: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_PUBSUB_TOPIC", "google_pubsub_topic"
        ),
    )
    google_pubsub_subscription: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_PUBSUB_SUBSCRIPTION", "google_pubsub_subscription"
        ),
    )
    webhook_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices("WEBHOOK_BASE_URL", "webhook_base_url"),
    )

    microsoft_client_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("MICROSOFT_CLIENT_ID", "microsoft_client_id"),
    )
    microsoft_client_secret: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "MICROSOFT_CLIENT_SECRET", "microsoft_client_secret"
        ),
    )
    microsoft_tenant: Optional[str] = Field(
        default="common",
        validation_alias=AliasChoices("MICROSOFT_TENANT", "microsoft_tenant"),
    )
    microsoft_redirect_uri: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "MICROSOFT_REDIRECT_URI", "microsoft_redirect_uri"
        ),
    )
    webhook_base_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("WEBHOOK_BASE_URL", "webhook_base_url"),
    )

    qdrant_api_key: Optional[str] = Field(default=None)
    gemini_api_key: Optional[str] = Field(default=None)
    embedding_dimension: int = Field(
        default=3072,
        validation_alias=AliasChoices("EMBEDDING_DIMENSION", "embedding_dimension"),
    )

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
    # Chat LLM switch — independent of llm_provider (embeddings fake/gemini).
    llm_chat_provider: str = Field(
        default="fake",
        validation_alias=AliasChoices("LLM_CHAT_PROVIDER", "llm_chat_provider"),
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("OPENROUTER_BASE_URL", "openrouter_base_url"),
    )
    llm_max_tool_call_rounds: int = Field(
        default=2,
        validation_alias=AliasChoices(
            "LLM_MAX_TOOL_CALL_ROUNDS", "llm_max_tool_call_rounds"
        ),
    )
    llm_chat_temperature: float = Field(
        default=0.3,
        validation_alias=AliasChoices(
            "LLM_CHAT_TEMPERATURE", "llm_chat_temperature"
        ),
    )
    llm_chat_max_tokens: int = Field(
        default=1500,
        validation_alias=AliasChoices("LLM_CHAT_MAX_TOKENS", "llm_chat_max_tokens"),
    )
    assistant_debug: bool = Field(
        default=False,
        validation_alias=AliasChoices("ASSISTANT_DEBUG", "assistant_debug"),
    )
    rag_debug_trace: bool = Field(
        default=False,
        validation_alias=AliasChoices("RAG_DEBUG_TRACE", "rag_debug_trace"),
    )

    environment: str = Field(default="development")
    cors_allowed_origins: str = Field(
        default="",
        validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "cors_allowed_origins"),
        description="Comma-separated browser origins allowed in non-dev (empty = deny all)",
    )
    rate_limit_per_minute: int = Field(
        default=120,
        validation_alias=AliasChoices("RATE_LIMIT_PER_MINUTE", "rate_limit_per_minute"),
    )

    tesseract_path: str = Field(default="/usr/bin/tesseract")
    ocr_language: str = Field(default="eng")
    ocr_timeout_seconds: int = Field(default=30)
    max_extracted_chars: int = Field(default=500000)

    identity_cache_ttl: int = Field(default=86400)
    acl_inheritance_cache_ttl: int = Field(default=600)
    acl_revalidation_interval_seconds: int = Field(default=900)
    
    # ------------------------------------------------------------------
    # Block D: Storage & Encryption
    # ------------------------------------------------------------------
    encryption_key_name: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("ENCRYPTION_KEY_NAME", "encryption_key_name"),
    )
    backup_bucket: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("BACKUP_BUCKET", "backup_bucket"),
    )
    backup_local_dir: str = Field(
        default=".backups",
        validation_alias=AliasChoices("BACKUP_LOCAL_DIR", "backup_local_dir"),
    )
    
    # ------------------------------------------------------------------
    # Block E: Chunking & Embeddings
    # ------------------------------------------------------------------
    chunk_size: int = Field(
        default=1000,
        validation_alias=AliasChoices("CHUNK_SIZE", "chunk_size"),
    )
    chunk_overlap: int = Field(
        default=200,
        validation_alias=AliasChoices("CHUNK_OVERLAP", "chunk_overlap"),
    )
    embedding_model_version: str = Field(
        default="v1",
        validation_alias=AliasChoices("EMBEDDING_MODEL_VERSION", "embedding_model_version"),
    )
    embedding_batch_size: int = Field(
        default=100,
        validation_alias=AliasChoices("EMBEDDING_BATCH_SIZE", "embedding_batch_size"),
    )
    embedding_dimensions: int = Field(
        default=3072,
        validation_alias=AliasChoices("EMBEDDING_DIMENSIONS", "embedding_dimensions"),
    )
    
    # ------------------------------------------------------------------
    # Block F: Lexical Search (OpenSearch)
    # ------------------------------------------------------------------
    opensearch_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENSEARCH_URL", "opensearch_url"),
    )
    opensearch_host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("OPENSEARCH_HOST", "opensearch_host"),
    )
    opensearch_port: int = Field(
        default=9200,
        validation_alias=AliasChoices("OPENSEARCH_PORT", "opensearch_port"),
    )
    opensearch_index_prefix: str = Field(
        default="snyq",
        validation_alias=AliasChoices("OPENSEARCH_INDEX_PREFIX", "opensearch_index_prefix"),
    )
    lexical_max_results: int = Field(
        default=100,
        validation_alias=AliasChoices("LEXICAL_MAX_RESULTS", "lexical_max_results"),
    )
    
    # ------------------------------------------------------------------
    # Block G: Vector Search (Qdrant)
    # ------------------------------------------------------------------
    qdrant_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("QDRANT_URL", "qdrant_url"),
    )
    qdrant_host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("QDRANT_HOST", "qdrant_host"),
    )
    qdrant_port: int = Field(
        default=6333,
        validation_alias=AliasChoices("QDRANT_PORT", "qdrant_port"),
    )
    qdrant_collection_prefix: str = Field(
        default="snyq",
        validation_alias=AliasChoices("QDRANT_COLLECTION_PREFIX", "qdrant_collection_prefix"),
    )
    vector_search_top_k: int = Field(
        default=10,
        validation_alias=AliasChoices("VECTOR_SEARCH_TOP_K", "vector_search_top_k"),
    )
    
    # ------------------------------------------------------------------
    # Block H: Graph Search (Neo4j)
    # ------------------------------------------------------------------
    graph_backend: str = Field(
        default="mock",
        validation_alias=AliasChoices("GRAPH_BACKEND", "graph_backend"),
    )
    neo4j_uri: str = Field(
        default="bolt://localhost:7687",
        validation_alias=AliasChoices("NEO4J_URI", "neo4j_uri"),
    )
    neo4j_user: str = Field(
        default="neo4j",
        validation_alias=AliasChoices("NEO4J_USER", "neo4j_user"),
    )
    neo4j_password: str = Field(
        default="",
        validation_alias=AliasChoices("NEO4J_PASSWORD", "neo4j_password"),
    )
    neo4j_database_prefix: str = Field(
        default="graph_tenant_",
        validation_alias=AliasChoices("NEO4J_DATABASE_PREFIX", "neo4j_database_prefix"),
    )
    neo4j_cache_ttl_seconds: int = Field(
        default=3600,
        validation_alias=AliasChoices("NEO4J_CACHE_TTL_SECONDS", "neo4j_cache_ttl_seconds"),
    )
    max_traversal_depth: int = Field(
        default=2,
        validation_alias=AliasChoices("MAX_TRAVERSAL_DEPTH", "max_traversal_depth"),
    )
    traversal_result_limit: int = Field(
        default=100,
        validation_alias=AliasChoices("TRAVERSAL_RESULT_LIMIT", "traversal_result_limit"),
    )
    
    # ------------------------------------------------------------------
    # Block I: Activity Signals (Postgres)
    # ------------------------------------------------------------------
    signals_backend: str = Field(
        default="mock",
        validation_alias=AliasChoices("SIGNALS_BACKEND", "signals_backend"),
    )
    privacy_threshold: int = Field(
        default=5,
        validation_alias=AliasChoices("PRIVACY_THRESHOLD", "privacy_threshold"),
    )
    retention_days: int = Field(
        default=90,
        validation_alias=AliasChoices("RETENTION_DAYS", "retention_days"),
    )
    high_privacy_retention_days: int = Field(
        default=30,
        validation_alias=AliasChoices("HIGH_PRIVACY_RETENTION_DAYS", "high_privacy_retention_days"),
    )
    freshness_sla_seconds: int = Field(
        default=900,
        validation_alias=AliasChoices("FRESHNESS_SLA_SECONDS", "freshness_sla_seconds"),
    )
    popularity_window_days: int = Field(
        default=30,
        validation_alias=AliasChoices("POPULARITY_WINDOW_DAYS", "popularity_window_days"),
    )

    # ------------------------------------------------------------------
    # Object storage bucket name (used by tests and real deployment)
    # ------------------------------------------------------------------
    bucket_name: str = Field(
        default="snyq-data",
        validation_alias=AliasChoices("BUCKET_NAME", "bucket_name"),
    )

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
        env_val = (os.environ.get("EMBEDDING_PROVIDER") or os.environ.get("embedding_provider") or "").strip().lower()
        if env_val:
            return env_val
        if getattr(self, "gemini_api_key", None) or os.environ.get("GEMINI_API_KEY"):
            return "gemini"
        if str(getattr(self, "llm_provider", "")).strip().lower() in ("gemini", "fake"):
            return str(self.llm_provider).strip().lower()
        return "fake"

    @property
    def embedding_model(self) -> str:
        return self.model_version

    @property
    def oidc_issuer(self) -> Optional[str]:
        return self.oauth_issuer_url

    @staticmethod
    def normalize_origin(origin: str) -> str:
        """Strip whitespace and trailing slash so browser Origin headers match."""
        return (origin or "").strip().rstrip("/")

    @property
    def cors_origins_list(self) -> list[str]:
        raw = (self.cors_allowed_origins or "").strip()
        if not raw:
            return []
        return [
            self.normalize_origin(origin)
            for origin in raw.split(",")
            if origin.strip()
        ]

    @property
    def effective_cors_origins(self) -> list[str]:
        """
        Browser-allowed origins: explicit CORS list + FRONTEND_URL + local dev hosts.

        FRONTEND_URL is merged so Render/Vercel only need one of CORS_ALLOWED_ORIGINS
        or FRONTEND_URL set correctly (both is fine).
        """
        seen: set[str] = set()
        merged: list[str] = []
        for origin in self.cors_origins_list:
            if origin and origin not in seen:
                seen.add(origin)
                merged.append(origin)
        frontend = self.normalize_origin(self.frontend_url or "")
        if frontend and frontend not in seen:
            seen.add(frontend)
            merged.append(frontend)
        if self.environment.lower() in ("development", "dev", "test", "staging"):
            for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
                if origin not in seen:
                    seen.add(origin)
                    merged.append(origin)
        return merged

    @property
    def scim_endpoint(self) -> Optional[str]:
        return self.scim_sync_endpoint

    # ------------------------------------------------------------------
    # Block K: Document Reader
    # ------------------------------------------------------------------
    # storage_backend is defined once under Block D (STORAGE_BACKEND).
    storage_endpoint: str = Field(default="localhost:9000")
    storage_access_key: str = Field(default="")
    storage_secret_key: str = Field(default="")
    storage_bucket: str = Field(default="documents")
    storage_secure: bool = Field(default=False)
    stream_threshold_bytes: int = Field(default=10 * 1024 * 1024)  # 10MB
    stream_chunk_bytes: int = Field(default=8192)
    acl_backend: str = Field(default_factory=_default_acl_backend)  # "mock" | "http" | "postgres"
    acl_service_url: str = Field(default="http://localhost:8000/acl")

    @model_validator(mode="after")
    def _assemble_control_plane_url(self) -> "Settings":
        if not self.control_plane_database_url:
            user = quote_plus(self.db_user)
            password = quote_plus(self.db_password)
            self.control_plane_database_url = (
                f"postgresql+asyncpg://{user}:{password}"
                f"@{self.db_host}:5432/{self.db_name}"
            )
        from app.storage.pg_connect import prepare_database_url

        self.control_plane_database_url = prepare_database_url(
            self.control_plane_database_url,
            fallback_cloud_url=self.supabase_db_url or "",
            pooler_url=self.supabase_pooler_url or "",
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