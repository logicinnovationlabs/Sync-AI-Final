-- Block I initial schema (Block D / PostgreSQL)
CREATE TABLE IF NOT EXISTS activity_config (
    tenant_id TEXT PRIMARY KEY,
    privacy_threshold INTEGER NOT NULL DEFAULT 5,
    retention_days INTEGER NOT NULL DEFAULT 90,
    high_privacy_retention_days INTEGER NOT NULL DEFAULT 30,
    enable_per_source_disablement BOOLEAN NOT NULL DEFAULT FALSE,
    disabled_sources JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS activity_events (
    event_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    actor_principal_id TEXT NOT NULL,
    object_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_system TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    session_id TEXT,
    context_json JSONB,
    privacy_level TEXT NOT NULL DEFAULT 'public',
    ttl_seconds INTEGER NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_activity_events_tenant_object
    ON activity_events (tenant_id, object_id);
CREATE INDEX IF NOT EXISTS idx_activity_events_tenant_actor
    ON activity_events (tenant_id, actor_principal_id);
CREATE INDEX IF NOT EXISTS idx_activity_events_ingested
    ON activity_events (tenant_id, ingested_at);

CREATE TABLE IF NOT EXISTS user_signal_cache (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    signal_blob JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS document_popularity (
    tenant_id TEXT NOT NULL,
    object_id TEXT NOT NULL,
    distinct_actor_count INTEGER,
    total_views INTEGER,
    last_viewed_at TIMESTAMPTZ,
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, object_id)
);
