"""Application configuration for Block I Activity / Signal Service."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings (env-overridable)."""

    # Storage backend: "mock" | "postgres"
    signals_backend: str = "mock"

    # Defaults (overridable per-tenant via activity_config)
    privacy_threshold: int = 5
    retention_days: int = 90
    high_privacy_retention_days: int = 30
    signal_cache_ttl_seconds: int = 300
    freshness_sla_seconds: int = 900  # 15 minutes

    # Sliding windows for popularity (days)
    popularity_window_days: int = 30

    # Postgres (Phase 2 / Block D)
    database_url: str = "postgresql://signals:signals@localhost:15433/block_i_signals"

    # Redis cache (optional; mock falls back to in-process)
    redis_url: Optional[str] = None
    cache_enabled: bool = True

    # Kafka / Event Hub
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_activity: str = "ingest.activity.v1"
    kafka_consumer_group: str = "block-i-activity-ingester"
    kafka_enabled: bool = False

    # Auth
    environment: str = "test"
    jwt_private_key_path: Optional[str] = None
    jwt_public_key_path: Optional[str] = None
    enforce_tenant_isolation: bool = True

    # Fixtures (Block Z path override)
    fixtures_path: Optional[str] = None

    # Retention job
    retention_job_interval_seconds: int = 3600

    # Observability
    service_port: int = 8089

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
