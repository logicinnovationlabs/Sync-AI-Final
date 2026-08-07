"""Application configuration for Block H Knowledge Graph Service."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings (env-overridable)."""

    # Graph backend: "mock" | "neo4j"
    graph_backend: str = "mock"

    # Neo4j connection (admin / default; per-tenant DB name is derived)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "blockh-dev-password"
    neo4j_database_prefix: str = "graph_tenant_"
    # Per-tenant driver cache TTL (seconds); Vishwas Tier-2: 30–60 min
    neo4j_cache_ttl_seconds: int = 1800

    # Optional Block D metadata / vault integration
    tenant_metadata_url: Optional[str] = None
    vault_enabled: bool = False

    # Traversal / search limits
    max_traversal_depth: int = 2
    traversal_result_limit: int = 100
    people_search_limit: int = 20
    related_default_limit: int = 50

    # Kafka / Redpanda (graph writer)
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_canonical: str = "ingest.canonical.v1"
    kafka_consumer_group: str = "block-h-graph-writer"

    # Auth
    environment: str = "test"
    jwt_private_key_path: Optional[str] = None
    jwt_public_key_path: Optional[str] = None
    enforce_tenant_isolation: bool = True

    # Fixtures (Block Z path override)
    fixtures_path: Optional[str] = None

    # Observability
    emit_graph_events: bool = False

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
