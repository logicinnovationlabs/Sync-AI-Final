# SynQ AI — Environment & Platform Decisions

**Last updated:** 2026-08-07  
**Repo:** Sync Ai Final (Block Z–O build)

---

## Single source of truth

Runtime configuration comes from **environment variables**. For local development, set them in `backend/.env` (gitignored). Use `backend/.env.example` as the template.

Never commit secrets. Never log secret values (`DB_PASSWORD`, API keys, connection strings with credentials, JWT material).

---

## Master required variables

| Category | Variable | Purpose |
|----------|----------|---------|
| Tenancy | `TENANT_METADATA_SERVICE_URL` | Tenant metadata / Block A router |
| Tenancy | `OAUTH_ISSUER_URL` | OAuth 2.1 / OIDC issuer |
| Tenancy | `SCIM_SYNC_ENDPOINT` | SCIM provisioning endpoint |
| Tenancy | `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` | RS256 signing keys |
| Tenancy | `SESSION_STORE_REDIS_URL` | Redis session store (`REDIS_URL` alias) |
| Storage | `DB_HOST` `DB_NAME` `DB_USER` `DB_PASSWORD` | Primary Postgres (password never hardcoded) |
| Storage | `OBJECT_STORE_CONNECTION_STRING` | MinIO / S3 / Azure Blob |
| Storage | `KMS_KEY_VAULT_URL` / `KMS_KEY_NAME` | Envelope encryption KMS |
| Connectors | `KAFKA_BROKERS` | Kafka / Redpanda / Event Hubs |
| Connectors | `KAFKA_TOPIC_RAW` / `KAFKA_TOPIC_CANONICAL` | Ingestion topics |
| Connectors | `CONNECTOR_RATE_LIMIT_PER_SOURCE` | e.g. `drive=100,slack=50` |
| Connectors | `VAULT_SECRET_PATH` | Connector secrets path prefix |
| Search | `LEXICAL_SEARCH_URL` | OpenSearch / Elasticsearch |
| Search | `VECTOR_SEARCH_URL` / `VECTOR_INDEX_NAME` | Qdrant / vector index (`QDRANT_*` aliases) |
| LLM | `LLM_PROVIDER` / `MODEL_VERSION` | Provider + embedding/model id |
| Observability | `OTLP_ENDPOINT` / `LOG_LEVEL` / `METRICS_NAMESPACE` | Telemetry |

Provider-conditional: if `LLM_PROVIDER=azure_openai`, set `AZURE_OPENAI_*`; if `anthropic`, set `ANTHROPIC_API_KEY`.

---

## Local deps (Docker)

From repo root (requires Docker Desktop):

```bash
docker compose -f docker-compose.deps.yml up -d
```

Services (see `docker-compose.deps.yml` + `otel-config.yaml`):

| Service | URL | Notes |
|---------|-----|-------|
| MinIO | http://localhost:9000 (UI :9001) | If port busy, reuse `block-d-verify-minio` |
| Vault | http://localhost:8200 | Dev token `root` |
| Redpanda | localhost:9092 | Kafka-compatible |
| OpenSearch | http://localhost:9200 | Lexical search |
| OTLP collector | http://localhost:4318 | Traces HTTP |

Already commonly running from backend compose: Redis `:6379`, Qdrant `:6333`, Postgres `:5432`.

### Example local values

See the table in the master local-dev guide, or copy from `backend/.env.example`.

Validate presence (never print secrets in CI logs beyond PRESENT/MISSING):

```bash
cd backend
python scripts/check_env_presence.py
```

---

## Phase 0 status (historical)

| ID | Item | Status |
|----|------|--------|
| 0.1 | Docker daemon | PASS |
| 0.2 | Supabase cloud via `SUPABASE_DB_URL` | PASS (a) |
| 0.3 | Qdrant compose | PASS |
| 0.4 | `backend/.env` presence | PASS |
| 0.5 | Exit gate | PARTIAL — `ai-knowledge-platform` decision still open |

**Supabase:** prefer `SUPABASE_DB_URL` for cloud connectivity checks. Local `DB_*` / `CONTROL_PLANE_DATABASE_URL` remain for control-plane Postgres on the developer machine.