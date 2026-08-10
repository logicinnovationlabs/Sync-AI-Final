# SynQ / Sync AI — Environment, Health & Signoff Validation Report

**Date:** 2026-08-07  
**Repo:** `D:\PROJECTS\Sync Ai Final`  
**Runner:** Windows / PowerShell; host Python 3.14 (limited); authoritative A/B/C via Docker `backend-test:signoff` (Python 3.12.13)  
**Scope:** Phases 1–5 — env validation, dependency health, Blocks Z/A–H/J signoff, architectural compliance  

---

## Executive Summary

**Overall readiness: CONDITIONAL PASS for implemented Blocks Z, A–H, and J.**

| Area | Status |
|------|--------|
| Environment (master required vars + JWT keys) | **PASS** — `check_env_presence.py` exit 0; all required PRESENT |
| Dependency services (`docker-compose.deps.yml` + local stack) | **PASS** — Vault, Redpanda, OpenSearch, OTEL, MinIO (`glean-data`), Redis, Qdrant, Postgres :5432/:5434/:5435 all OK |
| Signoff criteria (Z, A–H, J) | **PASS** on this run (E2 from prior 10-min evidence file; F/G/H Phase-1 mock backends) |
| Architectural compliance | **PARTIAL** — tenant/ACL/scopes solid; OTLP SDK not wired in apps; tool policies not implemented; A–C live in `backend/` not `services/block-*` |

**Headline test counts (gate criteria):**

| Block | Criteria | Result |
|-------|----------|--------|
| Z | Z1–Z3 | 3/3 PASS |
| A | A1–A5 | 5/5 PASS (Docker 3.12) |
| B | B1–B5 | 5/5 PASS (Docker 3.12; B6/B7 also PASS) |
| C | C1–C4 | 4/4 PASS (Docker 3.12; C5–C9 also PASS) |
| D | D1–D4 | 4/4 PASS (after MinIO verify user + pgcrypto) |
| E | E1–E4 | 4/4 PASS (E2 via prior e2_10min_results.json, not re-run) |
| F | F1–F4 | 4/4 PASS (SEARCH_BACKEND=mock) |
| G | G1–G4 | 4/4 PASS (VECTOR_DB_TYPE=mock) |
| H | H1–H3 | 3/3 PASS (GRAPH_BACKEND=mock) |
| J | J1–J4 | 4/4 PASS (15/15 tests after clearing host JWT_PUBLIC_KEY_PATH) |

**Host caveat:** Native pytest on Python 3.14 failed several ASGI/asyncio tests (Starlette/anyio weakref, Timeout should be used inside a task). Treat Docker 3.12 results as the signoff source of truth for Blocks A–C.

---

## Environment Validation

### backend/scripts/check_env_presence.py

```
env_file_configured: yes
backend_dot_env_file: PRESENT
--- required ---
(all listed keys): PRESENT
--- jwt key files ---
jwt_private_key_file: PRESENT
jwt_public_key_file: PRESENT
EXIT_CODE=0
```

### Required variables (master prompt / ENVIRONMENT.md)

| Variable | Status | Notes |
|----------|--------|-------|
| TENANT_METADATA_SERVICE_URL | PRESENT | |
| OAUTH_ISSUER_URL | PRESENT | Alias OIDC_ISSUER also accepted |
| SCIM_SYNC_ENDPOINT | PRESENT | Alias SCIM_ENDPOINT |
| JWT_PRIVATE_KEY_PATH | PRESENT | File resolves under backend/keys/ |
| JWT_PUBLIC_KEY_PATH | PRESENT | File resolves under backend/keys/ |
| SESSION_STORE_REDIS_URL | PRESENT | Alias REDIS_URL |
| DB_HOST | PRESENT | |
| DB_NAME | PRESENT | |
| DB_USER | PRESENT | |
| DB_PASSWORD | PRESENT | Value not printed |
| OBJECT_STORE_CONNECTION_STRING | PRESENT | Points at local MinIO |
| KMS_KEY_VAULT_URL | PRESENT | |
| KMS_KEY_NAME | PRESENT | |
| KAFKA_BROKERS | PRESENT | |
| KAFKA_TOPIC_RAW | PRESENT | |
| KAFKA_TOPIC_CANONICAL | PRESENT | |
| CONNECTOR_RATE_LIMIT_PER_SOURCE | PRESENT | |
| VAULT_SECRET_PATH | PRESENT | |
| LEXICAL_SEARCH_URL | PRESENT | |
| VECTOR_SEARCH_URL | PRESENT | Alias QDRANT_URL |
| VECTOR_INDEX_NAME | PRESENT | Alias QDRANT_COLLECTION_NAME |
| LLM_PROVIDER | PRESENT | Provider class: fake/local — conditional Azure/Anthropic keys N/A |
| MODEL_VERSION | PRESENT | |
| OTLP_ENDPOINT | PRESENT | |
| LOG_LEVEL | PRESENT | |
| METRICS_NAMESPACE | PRESENT | |

### Optional / conditional (status only)

| Variable | Status | Notes |
|----------|--------|-------|
| VAULT_URL / Azure vault client IDs | MISSING | Intentional for local MockVaultClient |
| OIDC_CLIENT_ID / OIDC_CLIENT_SECRET / SCIM_TOKEN | MISSING | Optional until SSO/SCIM auth wired |
| AZURE_OPENAI_* / ANTHROPIC_API_KEY | MISSING | Not required for LLM_PROVIDER=fake |
| GOOGLE_CLIENT_*, GEMINI_API_KEY, etc. | PRESENT | Optional surface |

### JWT key files

| Path setting | File on disk |
|--------------|--------------|
| JWT_PRIVATE_KEY_PATH | PRESENT |
| JWT_PUBLIC_KEY_PATH | PRESENT |

### config.py load and derived properties

| Check | Result |
|-------|--------|
| Settings() / get_settings() load | OK |
| redis_url == session_store_redis_url | OK |
| qdrant_url == vector_search_url | OK |
| control_plane_database_url | PRESENT |
| URL scheme postgresql+asyncpg:// | OK |
| Assembly from DB_* | N/A when CONTROL_PLANE_DATABASE_URL is set — explicit URL wins; observed hostname may differ from DB_HOST while DB name matches |

---

## Service Health

Verified existing containers plus docker-compose.deps.yml (already up). MinIO is block-d-verify-minio (compose skips MinIO when :9000 is taken).

| Service | Endpoint / check | Status | Notes |
|---------|------------------|--------|-------|
| Vault | http://localhost:8200/v1/sys/health | OK | HTTP 200 |
| Redpanda (Kafka) | TCP :9092 | OK | |
| OpenSearch | http://localhost:9200 | OK | HTTP 200 + cluster info |
| OTEL Collector | http://localhost:4318 | OK | HTTP 404 on root (expected); OTLP POST /v1/traces → 200 |
| MinIO | http://localhost:9000/minio/health/live | OK | HTTP 200; UI :9001 |
| MinIO bucket glean-data | list/create | OK | Already existed; also ensured block-d-verify |
| Redis | TCP :6379 | OK | snyq_redis_dev healthy |
| Qdrant | TCP :6333 + /readyz | OK | HTTP 200 |
| PostgreSQL (control-plane) | TCP :5432 | OK | snyq_postgres_dev healthy |
| block-a-verify-pg | TCP :5434 | OK | Used for A1–A5 |
| block-d-verify-pg | TCP :5435 | OK | Used for D1–D4; pgcrypto enabled this session |
| block_e_postgres | TCP :5433 | OK | Started for E3 |

Remediation applied during validation (ops only, not product code):

1. Created MinIO IAM user matching Block D2 hardcoded credentials (root remains minioadmin).
2. CREATE EXTENSION pgcrypto on block_d_verify.
3. Started block_e_postgres and aligned DB password for the E3 script URL.

---

## Signoff Test Results

Artifacts under `_validation_run/`.

### Block Z — Reference Fixtures and Contract Mocks

Suite: tests/test_blocks/test_block_z.py  
Command: python -m pytest tests/test_blocks/test_block_z.py -v

| ID | Criterion | Result | Notes |
|----|-----------|--------|-------|
| Z1 | Contracts present and parseable | PASS | >=10 OpenAPI contracts under contracts/ |
| Z2 | Fixture lint and versioning | PASS | fixtures/MANIFEST.json + lint OK |
| Z3 | Swap shape normalization | PASS | Mock/real shape compare |

Fixtures present: documents, principals, groups, acl_matrix, relevance_labels, acl_redteam_cases, graph_edges, multi_source_identities, performance_baselines, crawl_expectations.

---

### Block A — Tenancy, Identity, Auth

Suite: backend/tests/test_signoff_closeout_local.py  
Authoritative run: Docker backend-test:signoff → block-a-verify-pg:5434 + Redis  
Host 3.14: A1 PASS; A2–A5 FAIL (Starlette/anyio / asyncio) — ignored in favor of Docker

| ID | Criterion | Result | Notes |
|----|-----------|--------|-------|
| A1 | Tenant binding integrity | PASS | 100/100 tokens; single tenant_id; kid=key-2026-08 |
| A2 | Revocation latency | PASS | Docker; poll /api/v1/me |
| A3 | SCIM idempotency (process restart) | PASS | |
| A4 | Cross-tenant replay rejection | PASS | X-Tenant-ID mismatch → 403 |
| A5 | Scope enforcement | PASS | Scoped routes → 403 envelope |

```
Docker: 5 passed in 10.28s
```

---

### Block B — Connectors

Suite: backend/tests/test_signoff_block_b.py  
Authoritative: Docker 3.12 — 11 passed

| ID | Criterion | Result | Notes |
|----|-----------|--------|-------|
| B1 | Backfill completeness | PASS | Drive + Gmail |
| B2 | Webhook incremental correctness | PASS | |
| B3 | Webhook authenticity rejection | PASS | Host 3.14 failed; Docker PASS |
| B4 | Rate-limit resilience | PASS | |
| B5 | Credential leakage | PASS | |
| B6/B7 | Allowlist / watch renewal | PASS | Extra beyond B1–B5 gate |

---

### Block C — Normalization and ACL

Suite: backend/tests/test_signoff_block_c.py  
Authoritative: Docker 3.12 — 10 passed

| ID | Criterion | Result | Notes |
|----|-----------|--------|-------|
| C1 | Determinism | PASS | |
| C2 | ACL fidelity | PASS | |
| C3 | Revocation propagation | PASS | |
| C4 | Identity resolution accuracy | PASS | |
| C5–C9 | Cycle safety, MIME, bounds, races | PASS | Extra |

Host 3.14: C1–C4 PASS; C5/C6/C8 FAIL (Timeout should be used inside a task).

---

### Block D — Storage Substrate

Suite: services/block-d-storage/tests/test_D*_local.py  
Deps: Postgres :5435, MinIO :9000

| ID | Criterion | Result | Notes |
|----|-----------|--------|-------|
| D1 | Provisioning time | PASS | First run |
| D2 | Backup/restore integrity | PASS | After MinIO user + block-d-verify bucket |
| D3 | Storage-layer tenant isolation | PASS | First run |
| D4 | Key rotation under load | PASS | After pgcrypto enabled |

First-pass failures (resolved): D2 InvalidAccessKeyId (test expects credentials that differ from MinIO root); D4 missing pgcrypto.

---

### Block E — Chunking / Embedding

| ID | Criterion | Result | Command / evidence |
|----|-----------|--------|--------------------|
| E1 | Chunk integrity (AST) | PASS | verify_component4_code_chunker.py — 36 files, 428 chunks, 0 mid-split |
| E2 | Throughput 10-min | PASS* | Prior services/block-e-chunking/e2_10min_results.json (2026-08-05): agg 548.9 docs/min, worst window 546.3 >= 400, meets_target: true. *Not re-executed this session (~10 min).* |
| E3 | Re-embed trigger | PASS | verify_component6_re_embed_trigger.py against block_e_postgres:5433 |
| E4 | Idempotency | PASS | verify_e4_idempotency.py (UTF-8 console); identical chunk_ids x3 |

---

### Block F — Lexical Search

Suite: services/block-f-lexical-search/tests/ with SEARCH_BACKEND=mock  
Result: 7 passed (F1–F4 + tokenizer)

| ID | Criterion | Result | Notes |
|----|-----------|--------|-------|
| F1 | Latency p95 <= 200ms | PASS | Mock |
| F2 | ACL red-team 0 leaks | PASS | |
| F3 | Index lag | PASS | |
| F4 | Facet accuracy | PASS | |

Phase-2 OpenSearch integration: not re-run this session (OpenSearch health OK for a future run).

---

### Block G — Vector Search

Suite: services/block-g-vector-search/tests/ with VECTOR_DB_TYPE=mock  
Result: 4 passed

| ID | Criterion | Result |
|----|-----------|--------|
| G1 | Recall@10 | PASS |
| G2 | ACL prefilter | PASS |
| G3 | Latency p95 | PASS |
| G4 | Model-version handling | PASS |

Qdrant :6333 healthy for optional Phase-2 re-run.

---

### Block H — Knowledge Graph

Suite: services/block-h-graph/tests/ with GRAPH_BACKEND=mock  
Result: 3 passed

| ID | Criterion | Result |
|----|-----------|--------|
| H1 | Edge fidelity | PASS |
| H2 | Traversal latency | PASS |
| H3 | Merge/split integrity | PASS |

Neo4j Phase-2 not started this session.

---

### Block J — Query Federator

Suite: services/block-j-query-federator/tests/  
Result: 15 passed (after clearing host JWT_PUBLIC_KEY_PATH so test alg=none tokens work in ENVIRONMENT=test)

| ID | Criterion | Result | Notes |
|----|-----------|--------|-------|
| J1 | Latency p95 | PASS | Federator latency tests |
| J2 | Red-team 0 unauthorized | PASS | test_permission.py |
| J3 | NDCG@10 | PASS | Ranker tests |
| J4 | Graceful degradation | PASS | Kill-backend cases |

First-pass failure: test_api_search_endpoint → 401 when host JWT_PUBLIC_KEY_PATH pointed at a real PEM while tests mint alg=none JWTs. Cleared path → PASS.

---

### Blocks not in this gate

| Block | Status |
|-------|--------|
| I (Signals), K (Reader), L (Assistant), M (MCP), N (Admin), O (Observability product) | NOT_IMPLEMENTED as signoff suites in this run |

---

## Architectural Compliance

### Tenant isolation

- PASS: JWTs carry exactly one tenant_id; A1 validates 100/100.
- PASS: Cross-tenant replay rejected via require_matching_tenant / X-Tenant-ID (A4).
- PASS (API surface): Tenant create returns Vault key name (db_secret_key), not password.
- FINDING: TenantResolver caches db_password inside Redis routing blob — contradicts "cache everything except password" intent.

### Storage namespaces (Block D)

- PASS: Object paths tenant_<id>/…; DB schemas tenant_<id>; router returns vault refs, not secrets.
- Deviation (documented): pgcrypto used instead of pgsodium (PHASE_4_DEVIATIONS.md).

### Authorization layers

| Layer | Finding |
|-------|---------|
| Tenant isolation | Enforced (JWT + header match) |
| API scopes | require_scope on connectors + scoped probes (A5) |
| Object ACLs | Block C ACLCompiler; F/G filters; J permission post-check |
| Tool policies | MISSING in production code — only contract mock / MCP contract stub |

### Security

- Recent container logs (otel, vault, postgres, redis): no obvious secret-pattern dumps in last 100 lines.
- Local deps mostly plaintext (Redpanda PLAINTEXT, OpenSearch security disabled, Vault -dev, MinIO HTTP). Acceptable for local; not production posture.

### Observability

- Collector: OK; synthetic OTLP HTTP POST to :4318/v1/traces returned 200.
- App SDK: OTLP_ENDPOINT configured in Settings, but no OpenTelemetry TracerProvider/instrumentation found in app entrypoints — apps are not emitting traces yet.
- Block J has in-process metrics helpers (not OTLP export).

### Architecture alignment

| Spec expectation | Actual |
|------------------|--------|
| Per-block services/block-* | A–C in backend/; D–H, J under services/ |
| Polyglot persistence | Present: Postgres, MinIO/S3, OpenSearch (F), Qdrant (G + backend), Neo4j client (H) |
| Dual tenancy models | Backend per-tenant DB routing vs Block D schema-per-tenant — both exist |

---

## Recommendations

1. Standardize on Python 3.12 for backend signoff (Docker backend-test:signoff or install 3.12 locally). Do not treat host 3.14 ASGI failures as product regressions.
2. Wire OpenTelemetry SDK in backend + search/federator services to export to OTLP_ENDPOINT (collector is healthy; apps are not emitting).
3. Stop caching db_password in Redis in TenantResolver; keep vault pointer + non-secret routing only.
4. Align MinIO credentials for Block D tests with compose defaults or bootstrap the D2 IAM user in compose so D2 does not flake.
5. Enable pgcrypto in Block D verify DB init so D4 does not require a manual CREATE EXTENSION.
6. Re-run E2 live when scheduling allows (10-min sustained) to refresh evidence beyond 2026-08-05 JSON.
7. Phase-2 integration passes: F against OpenSearch, G against Qdrant, H against Neo4j — deps already healthy where applicable.
8. Block J test env: Document that JWT_PUBLIC_KEY_PATH must be unset (or use RS256 test tokens) when running federator tests with alg=none fixtures.
9. Tool-policy layer (MCP/admin): Still absent — track before Block M/N signoff.
10. Retire synthetic /api/v1/scoped/* probes once real search/document/admin routes carry the same scopes (noted in backend/SIGNOFF.md).

---

## Appendix — Commands Used (non-secret)

```powershell
# Env
cd backend; python scripts/check_env_presence.py

# Deps
docker compose -f docker-compose.deps.yml ps

# Block Z
python -m pytest tests/test_blocks/test_block_z.py -v

# Blocks A–C (Docker 3.12)
docker run --rm --add-host=host.docker.internal:host-gateway -v ${PWD}:/app -w /app `
  -e SNYQ_IGNORE_ENV_FILE=1 -e JWT_PRIVATE_KEY_PATH=/app/keys/private.pem ... `
  backend-test:signoff python -m pytest tests/test_signoff_closeout_local.py -v

# Block D
cd services/block-d-storage
python -m pytest tests/test_D1_provisioning_time_local.py tests/test_D2_backup_restore_local.py `
  tests/test_D3_storage_isolation_local.py tests/test_D4_key_rotation_local.py -v

# Blocks F/G/H/J (mock)
# SEARCH_BACKEND=mock | VECTOR_DB_TYPE=mock | GRAPH_BACKEND=mock | ENVIRONMENT=test
```

Evidence directory: `_validation_run/` (block_*.txt, check_env.txt).

---

*End of report.*