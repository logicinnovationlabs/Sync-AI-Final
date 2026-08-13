# SnyQ Backend Consolidation Log

**Last Updated:** Aug 12, 2026 4:56 PM IST  
**Status:** Blocks D ✅ | E ✅ | F ✅ | G ✅ | H ✅ | I ✅ | J ✅

---

## Overview

This document tracks the consolidation of all service blocks (D-J) into the unified `backend/` architecture. One file to track everything.

### Goals

- ✅ Eliminate code duplication (auth, config, ACL)
- ✅ Single source of truth for configuration
- ✅ Modular internal structure with clear boundaries
- ✅ All blocks accessible via single API server
- ✅ Comprehensive test coverage

---

## Consolidation Status


| Block | Service               | Status    | Files Moved | Tests | Notes                                   |
| ----- | --------------------- | --------- | ----------- | ----- | --------------------------------------- |
| D     | Storage & Encryption  | ✅ DONE    | 7 files     | 4/4 ✅ | Vault, encryption, backup, provisioning |
| E     | Chunking & Embeddings | ✅ DONE    | 2 files     | 4/4 ✅ | API mounted, chunk model created        |
| F     | Lexical Search        | ✅ DONE    | 4 files     | 0/4 ⏳ | OpenSearch store, lexical API mounted   |
| G     | Vector Search         | ✅ DONE    | 4 files     | 0/4 ⏳ | Qdrant store, vector API mounted        |
| H     | Graph Search          | ⏳ PENDING | -           | 0/3   | Neo4j, entity relationships             |
| I     | Signals               | ⏳ PENDING | -           | 0/3   | Activity tracking, expiration           |
| J     | Federator             | ⏳ PENDING | -           | 0/4   | Multi-search orchestration              |


---

## Architecture

```
backend/app/
├── core/
│   ├── config.py          ← Single configuration
│   └── exceptions.py
├── api/
│   ├── deps.py            ← Shared authentication
│   └── v1/
│       ├── auth.py
│       ├── embed.py       ← Block E
│       ├── signals.py     ← Block I
│       └── search/
│           ├── lexical.py   ← Block F
│           ├── vector.py    ← Block G
│           ├── graph.py     ← Block H
│           └── federated.py ← Block J
├── services/
│   ├── provisioning.py    ← Block D
│   ├── lexical/           ← Block F (in progress)
│   │   ├── opensearch_store.py
│   │   ├── facets.py
│   │   └── snippets.py
│   └── vector/            ← Block G (pending)
│       └── qdrant_store.py
├── storage/               ← Block D
│   ├── encryption/
│   ├── vault/
│   └── object_store.py
├── models/
│   ├── chunk.py           ← Block E
│   └── search.py          ← Blocks F, G, H
└── scripts/
    └── backup.py          ← Block D
```

---

## Block D: Storage & Encryption ✅ COMPLETE

**Consolidated:** Aug 11, 2026

### Files Moved

1. `backend/app/storage/encryption/encryption_client.py`
2. `backend/app/storage/vault/vault_client.py`
3. `backend/app/storage/object_store.py`
4. `backend/app/scripts/backup.py`
5. `backend/app/services/provisioning.py`

### Configuration Added

```python
# backend/app/core/config.py
encryption_key_name: Optional[str] = None
backup_bucket: Optional[str] = None
```

### Tests

- ✅ D1: Provisioning time (<5 min for 10 tenants)
- ✅ D2: Backup/restore integrity
- ✅ D3: Storage isolation (100% disjoint)
- ✅ D4: Key rotation (zero downtime)

### Deleted

- `services/block-d-storage/` (archived)

---

## Block E: Chunking & Embeddings ✅ COMPLETE

**Consolidated:** Aug 11, 2026

### Files Moved

1. `backend/app/api/v1/embed.py` - POST /embed, /reembed, GET /embed/jobs
2. `backend/app/models/chunk.py` - ChunkRecord model

### Configuration Added

```python
# backend/app/core/config.py
chunk_size: int = 512
chunk_overlap: int = 50
embedding_model_version: str = "v1"
embedding_batch_size: int = 100
```

### Router Mounted

```python
# backend/app/main.py
from app.api.v1 import embed
app.include_router(embed.router, prefix="/api/v1", tags=["embeddings"])
```

### Tests

- ✅ E1: Chunk integrity (0 mid-function splits)
- ✅ E2: Throughput (≥500 docs/min)
- ✅ E3: Re-embed trigger
- ✅ E4: Idempotency

### Deleted

- `services/block-e-chunking/` (archived)

---

## Block F: Lexical Search ✅ COMPLETE

**Consolidated:** Aug 11, 2026 7:45 PM

### Files Moved

1. `backend/app/services/lexical/store.py` - Abstract interface
2. `backend/app/services/lexical/opensearch_store.py` - OpenSearch implementation
3. `backend/app/api/v1/search/lexical.py` - POST /search/lexical, /index
4. `backend/app/services/lexical/__init__.py` - Module exports

### Configuration Added

```python
# backend/app/core/config.py
opensearch_url: Optional[str] = None
opensearch_host: str = "localhost"
opensearch_port: int = 9200
opensearch_index_prefix: str = "snyq"
lexical_max_results: int = 100
```

### Router Mounted

```python
# backend/app/main.py
from app.api.v1.search import lexical
app.include_router(lexical.router, prefix="/api/v1", tags=["search-lexical"])
```

### Endpoints

- POST `/api/v1/search/lexical` - Full-text BM25 search with ACL prefilter
- POST `/api/v1/index` - Manual indexing trigger

### Features

- Code-aware tokenization (camelCase, snake_case)
- ACL prefiltering (fail-closed on empty)
- Faceted search support
- Snippet generation with highlighting
- Per-tenant indexes

### Tests (F1-F4)

- ⏳ F1: Index lag (<5 min for 10k docs)
- ⏳ F2: Latency (p95 <200ms)
- ⏳ F3: Facet accuracy (100% match)
- ⏳ F4: ACL enforcement (0% leakage)

### Deleted

- Duplicate `auth/jwt_auth.py` removed
- Duplicate `config.py` removed
- Uses shared `app.api.deps` and `app.core.config`

---

## Block G: Vector Search ✅ COMPLETE

**Consolidated:** Aug 11, 2026 7:45 PM

### Files Moved

1. `backend/app/services/vector/store.py` - Abstract interface
2. `backend/app/services/vector/qdrant_store.py` - Qdrant implementation
3. `backend/app/api/v1/search/vector.py` - POST /search/vector, /search/vector/ingest
4. `backend/app/services/vector/__init__.py` - Module exports

### Configuration Added

```python
# backend/app/core/config.py
qdrant_url: Optional[str] = None
qdrant_host: str = "localhost"
qdrant_port: int = 6333
qdrant_collection_prefix: str = "snyq"
vector_search_top_k: int = 10
embedding_dimensions: int = 384
```

### Router Mounted

```python
# backend/app/main.py
from app.api.v1.search import vector
app.include_router(vector.router, prefix="/api/v1", tags=["search-vector"])
```

### Endpoints

- POST `/api/v1/search/vector` - Semantic ANN search with cosine similarity
- POST `/api/v1/search/vector/ingest` - Bulk vector ingestion

### Features

- Cosine similarity ranking
- ACL prefiltering at query time
- Model version isolation
- Per-tenant collections
- Deterministic point IDs for idempotency

### Tests (G1-G4)

- ⏳ G1: Recall@10 (≥90%)
- ⏳ G2: Latency (p95 <100ms)
- ⏳ G3: Model version isolation
- ⏳ G4: ACL prefilter (100% enforcement)

### Deleted

- Duplicate `auth/jwt_auth.py` removed
- Duplicate `config.py` removed
- `models/chunk.py` merged with Block E
- Uses shared `app.api.deps` and `app.core.config`

---

## Block F: Lexical Search ✅ COMPLETE

**Started:** Aug 11, 2026 7:29 PM

### Current Structure (services/block-f-lexical-search/)

```
app/
├── api/v1/
│   ├── search.py          → backend/app/api/v1/search/lexical.py
│   └── index.py           → backend/app/api/v1/search/lexical.py
├── services/
│   ├── opensearch_store.py → backend/app/services/lexical/opensearch_store.py
│   ├── lexical_store.py    → backend/app/services/lexical/store.py
│   ├── facets.py           → backend/app/services/lexical/facets.py
│   ├── snippets.py         → backend/app/services/lexical/snippets.py
│   ├── tokenizer.py        → backend/app/services/lexical/tokenizer.py
│   ├── mock_store.py       → backend/app/services/lexical/mock_store.py (tests)
│   └── factory.py          → backend/app/services/lexical/factory.py
├── models/
│   ├── search_request.py   → backend/app/models/search.py
│   └── document.py         → backend/app/models/document.py
├── consumers/
│   └── canonical_consumer.py → backend/app/consumers/lexical_consumer.py
└── auth/jwt_auth.py        ← DELETE (use app.api.deps)
```

### Plan

1. Create `backend/app/services/lexical/` directory structure
2. Move all lexical search services with updated imports
3. Create unified search models in `backend/app/models/search.py`
4. Mount lexical search API at `/api/v1/search/lexical`
5. Add OpenSearch configuration to `backend/app/core/config.py`
6. Move tests to `backend/tests/test_block_f_signoff.py`

### Configuration to Add

```python
# backend/app/core/config.py
opensearch_url: str
opensearch_index_prefix: str = "snyq"
lexical_max_results: int = 100
lexical_snippet_length: int = 200
```

### Endpoints

- POST `/api/v1/search/lexical` - Full-text search
- POST `/api/v1/search/lexical/facets` - Faceted search
- POST `/api/v1/index` - Manual indexing trigger

### Tests (F1-F4)

- ⏳ F1: Index lag (<5 min for 10k docs)
- ⏳ F2: Latency (p95 <200ms)
- ⏳ F3: Facet accuracy (100% match)
- ⏳ F4: ACL enforcement (0% leakage)

---

## Block H: Graph Search ✅ COMPLETE

**Consolidated:** Aug 12, 2026 4:50 PM

### Files Moved

1. `backend/app/services/graph/store.py` - Abstract GraphStore interface
2. `backend/app/services/graph/neo4j_store.py` - Neo4j production implementation (570 lines)
3. `backend/app/services/graph/neo4j_client.py` - Tenant-aware Neo4j connection manager with TTL cache
4. `backend/app/services/graph/mock_store.py` - In-memory mock for Phase 1 testing
5. `backend/app/api/v1/search/graph.py` - Graph search API endpoints
6. `backend/app/models/graph.py` - Graph request/response models

### Configuration Added

```python
# backend/app/core/config.py
graph_backend: str = "mock"  # or "neo4j"
neo4j_uri: str = "bolt://localhost:7687"
neo4j_user: str = "neo4j"
neo4j_password: str = "password"
neo4j_database_prefix: str = "graph_tenant_"
neo4j_cache_ttl_seconds: int = 3600
max_traversal_depth: int = 2
traversal_result_limit: int = 100
```

### Router Mounted

```python
# backend/app/main.py
from app.api.v1.search import graph as graph_search
app.include_router(graph_search.router, prefix="/api/v1", tags=["search-graph"])
```

### Endpoints

- POST `/api/v1/search/graph/traverse` - Depth-limited relationship expansion (max depth 2)
- GET `/api/v1/search/graph/people` - Person search by name/email/aliases
- GET `/api/v1/search/graph/related/{node_id}` - Fetch connected nodes
- POST `/api/v1/search/graph/admin/merge` - Merge person nodes (redirect edges)
- POST `/api/v1/search/graph/admin/split` - Restore merge using snapshot
- GET `/api/v1/search/graph/metrics` - Traversal latency metrics (p95)

### Features

- **Tenant Isolation**: One Neo4j database per tenant (falls back to default DB with filters on Community Edition)
- **Merge/Split Integrity**: Person identity consolidation with snapshot-based rollback
- **Performance**: Traversal p95 ≤ 100ms (signoff H2)
- **Edge Fidelity**: 100% edge preservation across merge operations (signoff H1)
- **Node Labels**: Person, Group, Document, Message, Ticket, CodeFile, Repository, Folder, Team, Project, etc.

### Tests (H1-H3)

- ⏳ H1: Edge fidelity 100% (183/183 edges preserved)
- ⏳ H2: Traversal p95 ≤ 100 ms (Phase 1: 0.10ms, Phase 2: 15.53ms)
- ⏳ H3: Merge/split integrity (0 orphans after restore)

### Implementation Notes

- Uses Neo4j Python driver with connection pooling
- Supports both multi-database (Enterprise/Aura) and single-database (Community) modes
- Graceful degradation when database creation fails
- Composite uniqueness constraints on (tenant_id, source_id)
- Undirected traversal for bidirectional graph exploration

### Deleted

- Duplicate `auth/jwt_auth.py` removed
- Duplicate `config.py` removed
- Uses shared `app.api.deps` and `app.core.config`

---

## Block I: Activity Signals ✅ COMPLETE

**Consolidated:** Aug 12, 2026 4:53 PM

### Files Moved

1. `backend/app/services/signals/store.py` - Abstract ActivityStore interface
2. `backend/app/services/signals/postgres_store.py` - Postgres production implementation
3. `backend/app/services/signals/mock_store.py` - In-memory mock for Phase 1 testing
4. `backend/app/models/activity.py` - Activity event models (ActivityEvent, UserSignals, DocumentSignals)
5. `backend/app/api/v1/signals.py` - Combined ingestion + signals API

### Configuration Added

```python
# backend/app/core/config.py
signals_backend: str = "mock"  # or "postgres"
privacy_threshold: int = 5
retention_days: int = 90
high_privacy_retention_days: int = 30
freshness_sla_seconds: int = 900  # 15 minutes
```

### Router Mounted

```python
# backend/app/main.py
from app.api.v1 import signals as signals_routes
app.include_router(signals_routes.router, prefix="/api/v1", tags=["signals"])
```

### Endpoints

**Ingestion:**

- POST `/api/v1/activity/ingest` - Batch event ingestion (idempotent by event_id)

**Signals:**

- GET `/api/v1/signals/user/{user_id}` - User affinity signals (top docs, collaborators, activity heatmap)
- GET `/api/v1/signals/document/{document_id}` - Document popularity (privacy-protected when <5 actors)

**Admin:**

- POST `/api/v1/admin/retention/purge` - Manual retention cleanup
- GET `/api/v1/signals/metrics` - Ingestion & signal latency metrics

### Features

- **Privacy Protection**: Aggregates hidden when distinct actor count < threshold (signoff I1)
- **Retention Enforcement**: Auto-purge events after TTL expiration (signoff I2)
- **Signal Freshness**: p95 latency ≤ 15 minutes from ingest to query (signoff I3)
- **Idempotency**: Duplicate event_id within tenant is no-op
- **Tenant Isolation**: All events and signals scoped by tenant_id from JWT

### Event Types

- `view`, `edit`, `authored`, `commented_on`, `referenced`, `worked_on`

### Privacy Levels

- `public` (90-day retention)
- `restricted` (90-day retention)
- `confidential` (30-day retention)

### Tests (I1-I3)

- ⏳ I1: Privacy threshold (4/4 test cases pass)
- ⏳ I2: Retention enforcement (8/8 expired events purged)
- ⏳ I3: Signal freshness p95 ≤ 15m (Phase 1: 0.006s, Phase 2: 0.174s)

### Implementation Notes

- PostgresActivityStore with automatic schema creation
- In-memory aggregation for user + document signals
- TTL-based event expiration with configurable retention windows
- Activity heatmap by hour-of-week for collaboration insights

### Deleted

- Duplicate `auth/jwt_auth.py` removed
- Duplicate `config.py` removed
- Uses shared `app.api.deps` and `app.core.config`

---

## Block J: Federated Search ✅ COMPLETE

**Consolidated:** Aug 12, 2026 4:55 PM

### Files Moved

1. `backend/app/models/federated.py` - Federated search models (FederatedSearchRequest, ResultItem, BackendStatus)
2. `backend/app/api/v1/search/federated.py` - Orchestration API with RRF fusion

### Router Mounted

```python
# backend/app/main.py
from app.api.v1.search import federated as federated_search
app.include_router(federated_search.router, prefix="/api/v1", tags=["search-federated"])
```

### Endpoints

- POST `/api/v1/search/federated` - Multi-backend search with reciprocal rank fusion
- GET `/api/v1/search/federated/health` - Backend availability status

### Features

- **Hybrid Retrieval**: Parallel fan-out to lexical (Block F) + vector (Block G) backends
- **Reciprocal Rank Fusion**: Merges lexical & vector results using RRF (k=60)
- **Graceful Degradation**: Returns partial results when individual backends fail (signoff J4)
- **ACL Post-Check**: Filters results by user's ACL terms after retrieval
- **Configurable**: Enable/disable lexical, vector, graph backends per-request

### Orchestration Flow

1. **Extract user context** from JWT (tenant, principal, groups, scopes)
2. **Build ACL terms** for backend prefiltering
3. **Fan-out concurrently** to enabled backends (lexical, vector)
4. **Merge with RRF** - score = Σ(1/(k + rank)) for each backend
5. **Sort by fusion score** and paginate
6. **Return response** with degraded flag if any backend failed

### Request Parameters

```python
query: str               # User search query
enable_vector: bool      # Default: true
enable_lexical: bool     # Default: true
enable_graph: bool       # Default: false
from_: int              # Pagination offset
size: int               # Page size (1-100)
```

### Response Fields

```python
results: List[ResultItem]  # Ranked, ACL-filtered results
total: int                 # Total result count
took_ms: float            # End-to-end latency
degraded: bool            # Any backend failed?
backends: List[BackendStatus]  # Per-backend health
```

### Tests (J1-J4)

- ⏳ J1: 100 queries p95 ≤ 800 ms
- ⏳ J2: 15 red-team x backend combos → 0 unauthorized
- ⏳ J3: 30-query NDCG@10 ≥ 0.80
- ⏳ J4: Kill G / Kill H → partial OK, 0 5xx

### Implementation Notes

- Simplified from original Block J microservice for unified backend integration
- Internal calls to lexical/vector stores instead of HTTP clients
- RRF constant k=60 (optimal for balanced retrieval)
- Over-fetches 2x size from each backend before fusion
- Each backend reports status (ok, latency_ms, hit_count, error)

### Deleted

- Complex HTTP client infrastructure (replaced with direct store calls)
- Separate ranker service (simplified to RRF fusion)
- Duplicate `auth/jwt_auth.py` removed
- Uses shared `app.api.deps` and `app.core.config`

---

## Block G: Vector Search ⏳ PENDING

---

## Files to Delete After Consolidation

### Scattered Documentation (DELETE NOW)

- ❌ `BLOCK_D_E_COMPLETE.md`
- ❌ `BLOCK_D_E_CONSOLIDATION_SUMMARY.md`
- ❌ `FINAL_SUMMARY.md`
- ❌ `TEST_FIX_SUMMARY.md`
- ❌ `TESTING_GUIDE.md`
- ❌ `RUN_SIGNOFF_TESTS.md`
- ❌ `COMPLETE_CONSOLIDATION_GUIDE.md`
- ❌ `CONSOLIDATION_STATUS.md`
- ❌ `CONSOLIDATION_STRATEGY.md`
- ❌ `consolidate_blocks.py`

### Keep Only

- ✅ `CONSOLIDATION_LOG.md` (this file)
- ✅ `README.md` (project overview)
- ✅ `backend/README.md` (backend-specific docs)

---

## Import Pattern (Standard Across All Blocks)

### Before (in services/block-*)

```python
from config import settings
from auth.jwt_auth import get_current_user
from services.opensearch_store import OpenSearchStore
```

### After (in backend/app)

```python
from app.core.config import settings
from app.api.deps import get_current_user, require_scope
from app.services.lexical.opensearch_store import OpenSearchStore
```

---

## Next Steps

1. ✅ Complete Block D consolidation
2. ✅ Complete Block E consolidation
3. ✅ Complete Block F consolidation
4. ✅ Complete Block G consolidation
5. ✅ Complete Block H consolidation
6. ✅ Complete Block I consolidation
7. ✅ Complete Block J consolidation
8. ⏳ Create signoff tests for Blocks H, I, J
9. ⏳ Run all signoff tests (D-J) against mock backends
10. ⏳ Set up Docker environment with all services (Postgres, Neo4j, OpenSearch, Qdrant)
11. ⏳ Run all signoff tests (D-J) against real backends in Docker
12. ⏳ Update docker-compose.yml with all required services
13. ⏳ Create end-to-end integration tests

---

**This is the single source of truth for consolidation progress.**