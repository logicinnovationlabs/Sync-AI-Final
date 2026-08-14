# Complete Project Structure - SnyQ Phase 2 Backend

**Date:** August 14, 2026  
**Architecture:** Monolithic FastAPI Application

---

## Root Structure

```
SnyQ_Phase_2/
└── backend/                    ← DEPLOYMENT ROOT (only this folder deploys)
    ├── app/                    ← Application code
    ├── tests/                  ← All tests (Blocks A-L)
    ├── migrations/             ← Alembic database migrations
    ├── scripts/                ← Utility scripts
    ├── requirements.txt        ← Python dependencies
    ├── pyproject.toml          ← Poetry configuration
    ├── .env.example            ← Environment template
    ├── deploy.ps1              ← Deployment script
    ├── run_tests.ps1           ← Test runner script
    └── [Documentation files]
```

---

## Application Structure (app/)

```
app/
├── main.py                     ← FastAPI application entry point
│
├── core/                       ← SHARED: Config, models, exceptions
│   ├── config.py               ← Single Settings class (all blocks)
│   ├── base_connector.py       ← Base connector interface
│   ├── exceptions.py           ← Custom exceptions
│   ├── errors.py               ← Error response models
│   └── models.py               ← Shared Pydantic models
│
├── api/                        ← API Layer
│   ├── deps.py                 ← SHARED: Auth dependencies (get_current_user, get_tenant)
│   └── v1/                     ← API v1 endpoints
│       ├── auth.py             ← Block A: Authentication
│       ├── oauth.py            ← Block B: OAuth
│       ├── acl.py              ← Block C: ACL
│       ├── identity.py         ← Identity resolution
│       ├── me.py               ← User profile
│       ├── admin.py            ← Admin endpoints
│       ├── connectors.py       ← Connector management
│       ├── embed.py            ← Embedding endpoints
│       ├── signals.py          ← Block I: Activity signals
│       ├── scoped_probes.py    ← Scoped probes
│       ├── document.py         ← Block K: Document Reader
│       └── search/             ← Search endpoints
│           ├── lexical.py      ← Block F: Lexical search
│           ├── vector.py       ← Block G: Vector search
│           ├── graph.py        ← Block H: Graph search
│           └── federated.py    ← Block J: Federated search
│
├── services/                   ← Business Logic Layer
│   ├── lexical/                ← Block F: Lexical search logic
│   │   └── opensearch_store.py
│   ├── vector/                 ← Block G: Vector search logic
│   │   └── qdrant_store.py
│   ├── signals/                ← Block I: Activity signals logic
│   │   ├── models.py
│   │   ├── capture.py
│   │   └── boost.py
│   ├── document_reader/        ← Block K: Document reader logic
│   │   ├── __init__.py
│   │   ├── reader.py           ← Core reading logic
│   │   ├── store.py            ← Storage (MinIO/mock)
│   │   └── acl_checker.py      ← ACL re-check
│   ├── assistant/              ← Block L: Assistant orchestrator
│   │   ├── api/
│   │   │   └── routes.py       ← Assistant endpoints
│   │   ├── core/
│   │   │   └── graph.py        ← LangGraph orchestration
│   │   ├── domain/
│   │   │   └── models.py       ← Domain models
│   │   └── infrastructure/
│   │       └── tools.py        ← Tool routing (calls J, H, K, I)
│   ├── pipeline.py             ← Block C: Pipeline orchestration
│   ├── normalizer.py           ← Block C: Document normalization
│   ├── text_extractor.py       ← Block C: Text extraction
│   ├── mime_detector.py        ← Block C: MIME detection
│   ├── identity_resolver.py    ← Identity resolution
│   ├── tenant_resolver.py      ← Tenant routing
│   ├── token_service.py        ← JWT token service
│   └── cursor_store.py         ← Sync cursor storage
│
├── acl/                        ← Block C: ACL Implementation
│   ├── compiler.py             ← ACL compilation
│   ├── inheritance.py          ← Permission inheritance
│   └── container_service.py    ← Container hierarchy
│
├── connectors/                 ← External Connectors (Block B)
│   ├── google/
│   │   ├── oauth.py            ← Google OAuth
│   │   ├── webhooks.py         ← Google webhooks
│   │   ├── watch_manager.py    ← Watch notifications
│   │   ├── clients/
│   │   │   ├── drive_client.py ← Google Drive client
│   │   │   └── gmail_client.py ← Gmail client
│   │   └── services/
│   │       ├── drive_service.py
│   │       └── gmail_service.py
│   └── [Other connectors]
│
├── identity/                   ← Identity Resolution
│   ├── resolver.py             ← Main resolver
│   ├── models.py               ← Identity models
│   └── matchers/
│       ├── email_matcher.py
│       └── username_matcher.py
│
├── models/                     ← Database Models
│   ├── base.py                 ← SQLAlchemy base
│   ├── tenant.py               ← Tenant model
│   ├── user.py                 ← User model
│   ├── group.py                ← Group model
│   ├── oauth_client.py         ← OAuth clients
│   ├── refresh_token.py        ← Refresh tokens
│   ├── scope.py                ← Scopes
│   ├── connector.py            ← Connector configurations
│   ├── watch.py                ← Watch subscriptions
│   ├── document.py             ← Document metadata
│   └── activity.py             ← Activity signals
│
├── storage/                    ← Storage Clients
│   ├── control_plane_db.py     ← Control plane DB
│   ├── tenant_db.py            ← Tenant DB manager
│   ├── redis_client.py         ← Redis client
│   ├── opensearch_client.py    ← OpenSearch client
│   ├── qdrant_client.py        ← Qdrant client
│   ├── neo4j_client.py         ← Neo4j client
│   └── vault_client.py         ← Azure Key Vault client
│
├── middleware/                 ← FastAPI Middleware
│   ├── tenant_middleware.py    ← Tenant context
│   └── scope_middleware.py     ← Scope validation
│
└── workers/                    ← Celery Workers (Block E)
    ├── chunking_worker.py      ← Document chunking
    ├── embedding_worker.py     ← Vector embedding
    └── sync_worker.py          ← Connector sync
```

---

## Test Structure (tests/)

```
tests/
├── conftest.py                 ← SHARED: Fixtures for all blocks
│
├── fixtures/                   ← Test fixtures
│   ├── google/
│   │   ├── drive/
│   │   └── gmail/
│   └── [Other fixtures]
│
├── test_signoff.py             ← Blocks A-J: Signoff tests (passing)
│
├── test_block_a.py             ← Block A: Tenancy & Identity tests
├── test_block_b.py             ← Block B: OAuth tests
├── test_block_c.py             ← Block C: ACL tests
├── test_block_k.py             ← Block K: Document Reader tests ✅
├── test_block_l.py             ← Block L: Assistant tests ✅
│
├── test_acl_compiler.py        ← ACL compiler unit tests
├── test_container_service.py   ← Container service tests
├── test_identity_resolver.py   ← Identity resolver tests
├── test_tenant_resolver.py     ← Tenant resolver tests
├── test_token_service.py       ← Token service tests
├── test_mime_detector.py       ← MIME detection tests
├── test_text_extractor.py      ← Text extraction tests
├── test_normalizer*.py         ← Normalizer tests
├── test_pipeline*.py           ← Pipeline tests
└── [Other test files]
```

---

## Key Files

### Configuration
- `.env.example` - Environment variable template (all blocks)
- `requirements.txt` - Python dependencies (pip)
- `pyproject.toml` - Poetry configuration
- `alembic.ini` - Database migration config

### Scripts
- `deploy.ps1` - Automated deployment script
- `run_tests.ps1` - Test runner with block selection
- `fix-install.bat` - Fix installation issues
- `test-block-*.bat` - Individual block test runners

### Documentation
- `README.md` - Main project documentation
- `QUICKSTART.md` - Quick start guide
- `INSTALL.md` - Installation instructions
- `DEPLOYMENT_READY.md` - Deployment guide
- `TESTS_COMPLETE.md` - Complete test documentation
- `TESTS_CONSOLIDATED.md` - Test consolidation summary
- `FINAL_FIXES_SUMMARY.md` - All fixes applied

### Docker
- `Dockerfile` - Production Docker image
- `Dockerfile.dev` - Development Docker image
- `Dockerfile.test` - Test Docker image
- `docker-compose.yml` - Production compose
- `docker-compose.dev.yml` - Development compose

---

## Block Mapping

| Block | Component | Location | API Endpoint |
|-------|-----------|----------|--------------|
| **A** | Tenancy & Identity | `api/v1/auth.py`, `services/tenant_resolver.py` | `/api/v1/auth/*` |
| **B** | OAuth Integration | `api/v1/oauth.py`, `connectors/google/` | `/api/v1/oauth/*` |
| **C** | ACL Compiler | `api/v1/acl.py`, `acl/`, `services/pipeline.py` | `/api/v1/acl/*` |
| **D** | Document Store | `models/document.py`, `storage/` | Internal |
| **E** | Chunking | `workers/chunking_worker.py` | Internal |
| **F** | Lexical Search | `api/v1/search/lexical.py`, `services/lexical/` | `/api/v1/search/lexical` |
| **G** | Vector Search | `api/v1/search/vector.py`, `services/vector/` | `/api/v1/search/vector` |
| **H** | Graph Search | `api/v1/search/graph.py` | `/api/v1/search/graph` |
| **I** | Activity Signals | `api/v1/signals.py`, `services/signals/` | `/api/v1/signals/*` |
| **J** | Federated Search | `api/v1/search/federated.py` | `/api/v1/search/federated` |
| **K** | Document Reader | `api/v1/document.py`, `services/document_reader/` | `/api/v1/document/{id}` |
| **L** | Assistant | `services/assistant/` | `/api/v1/assistant/*` |

---

## Shared Components (Used by ALL Blocks)

### Core Infrastructure
- `app/core/config.py` - Single Settings class
- `app/api/deps.py` - Auth dependencies (get_current_user, get_tenant)
- `app/models/` - Database models
- `app/storage/` - Storage clients

### Used By
- **Config**: All blocks read from `app.core.config.Settings`
- **Auth**: All endpoints use `app.api.deps.get_current_user`
- **Models**: All blocks use shared database models
- **Storage**: All blocks use shared storage clients

---

## Database Schema

### Control Plane (PostgreSQL)
- `tenants` - Tenant metadata
- `users` - User accounts
- `groups` - User groups
- `group_memberships` - Group membership
- `oauth_clients` - OAuth client configurations
- `refresh_tokens` - OAuth refresh tokens
- `scopes` - Permission scopes
- `connectors` - Connector configurations
- `watches` - Webhook subscriptions
- `sync_cursors` - Sync state tracking

### Tenant Databases (PostgreSQL - per tenant)
- `documents` - Document metadata (Block D)
- `chunks` - Document chunks (Block E)
- `activities` - Activity signals (Block I)

### Search Stores
- **OpenSearch** - Lexical search index (Block F)
- **Qdrant** - Vector embeddings (Block G)
- **Neo4j** - Knowledge graph (Block H)
- **Redis** - Caching layer

### Object Storage
- **MinIO/S3** - Document binaries (Block K)

---

## Dependencies

### Core
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pydantic` - Data validation
- `sqlalchemy` - ORM
- `alembic` - Migrations
- `asyncpg` - PostgreSQL async driver

### Block-Specific
- `langgraph>=0.2` - Block L: Assistant orchestration
- `langchain-core>=0.2` - Block L: LLM integration
- `minio>=7.2.0` - Block K: Object storage
- `psycopg[binary]>=3.1` - Block K: PostgreSQL
- `opensearch-py>=2.3.0` - Block F: Lexical search
- `qdrant-client` - Block G: Vector search
- `neo4j>=5.15.0` - Block H: Graph search
- `python-magic-bin` - Block C: MIME detection
- `celery` - Block E: Task queue

### Testing
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `httpx` - HTTP client

---

## Environment Variables

See `.env.example` for complete list. Key variables:

### Database
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `CONTROL_PLANE_DATABASE_URL`

### Authentication
- `JWT_SECRET_KEY`
- `OAUTH_ISSUER_URL`

### Search
- `OPENSEARCH_URL` - Block F
- `QDRANT_URL` - Block G
- `NEO4J_URI` - Block H

### Storage
- `STORAGE_BACKEND` - Block K (mock/minio)
- `STORAGE_ENDPOINT`, `STORAGE_BUCKET` - Block K

### Block L
- `QUERY_FEDERATOR_URL=http://localhost:8000/api/v1`
- `GRAPH_SERVICE_URL=http://localhost:8000/api/v1`
- `DOCUMENT_READER_URL=http://localhost:8000/api/v1`
- `SIGNALS_URL=http://localhost:8000/api/v1`

---

## Deployment

### Production
```powershell
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker
```bash
docker build -t snyq-backend .
docker run -p 8000:8000 snyq-backend
```

### Development
```powershell
cd backend
.\deploy.ps1
```

---

## Architecture Principles

1. **Monolithic Structure**: All blocks in one deployable unit (`backend/`)
2. **Shared Infrastructure**: One config, one auth, shared models
3. **Block Modularity**: Block-specific logic in `app/services/{block}/`
4. **No Code Duplication**: Common code in `app/core/`, `app/api/deps.py`
5. **Single Test per Block**: `test_block_x.py` for each block
6. **Environment-Based Config**: All config via `.env` file

---

**Total Lines of Code**: ~50,000+ (estimated)  
**Total Files**: ~200+ Python files  
**Blocks Integrated**: A through L (12 blocks)  
**Test Coverage**: Comprehensive (unit + integration tests)

**Status**: Production Ready ✅
