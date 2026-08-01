# SnyQ Phase 2 Backend - Blocks A + B

**Version:** 0.2.0  
**Build:** Block A (Tenancy, Identity, Auth) + Block B (Google Connector + Push Ingestion)

---

## Overview

This is the Python backend foundation for a Glean-like enterprise knowledge platform, implementing:

- **Block A** (Tenancy, Identity, Auth) - Multi-tenant auth with OIDC/SSO and native email/password
- **Block B** (Google Connector Package) - Push-based ingestion for Google Drive & Gmail with Celery workers

### Architecture Principles

1. **Blind Orchestrator Rule** — `core/`, `services/sync.py`, `services/indexer.py` never import specific connectors by name. Adding connector #11 requires zero edits to any core file.

2. **Tenant Boundary vs. Business Logic** — Tenant isolation (one tenant can never read another's data) is enforced by `tenant_id` binding in every JWT and every storage call. Document-level ACLs are a separate business-logic concern.

3. **Tier 2 Tenancy** — Each tenant gets its own Postgres database (`isolated_db` mode), not a shared schema with `tenant_id` filters.

4. **Vault-based Secrets** — The `tenants` table stores **Vault key names** (e.g., `kv/tenantA/db_password`), never actual passwords.

5. **Per-tenant Cache Partitioning** — Redis cache keys are namespaced as `tenant:{tenant_id}:*` to prevent cross-tenant leaks.

6. **Push-Driven Ingestion** (Block B) — After one-time backfill, Google tells us when content changes via webhooks. We only fetch the delta, never re-scan everything.

---

## Tech Stack

### Block A (Tenancy, Identity, Auth)
- **Python 3.12** with FastAPI (fully async)
- **Poetry** for dependency management
- **PostgreSQL** (asyncpg + SQLAlchemy 2.0 async ORM) — one DB per tenant
- **Redis** (async) for sessions, per-tenant cache, revocation
- **Vault abstraction** — `AzureKeyVaultClient` + `MockVaultClient` (env-var backed for dev)
- **python-jose** (RS256) for JWTs
- **Alembic** for migrations
- **pytest + pytest-asyncio** for tests

### Block B (Google Connector + Push Ingestion) 🆕
- **Celery** (Redis broker) for async task processing
- **google-api-python-client** for Drive & Gmail APIs
- **Qdrant** vector database for document embeddings
- **google-generativeai** (Gemini) for embeddings
- **Push notifications** via Drive watch channels & Gmail Pub/Sub
- **Docker Compose** with Qdrant, Celery worker, Celery beat

---

## Project Structure

```
backend/
├── app/
│   ├── core/                   # Config, contracts, exceptions
│   │   ├── base_connector.py   # BaseConnector ABC (blind orchestrator contract)
│   │   ├── config.py           # Pydantic Settings
│   │   ├── exceptions.py       # Custom exceptions
│   │   └── errors.py           # Error envelope schema
│   ├── models/                 # SQLAlchemy models
│   │   ├── tenant.py           # Tenant (control-plane DB)
│   │   ├── user.py             # User (per-tenant DB)
│   │   ├── group.py            # Group, GroupMembership
│   │   ├── oauth_client.py     # OAuthClient, RefreshToken
│   │   └── scope.py            # ScopeRegistry
│   ├── storage/                # Storage infrastructure
│   │   ├── control_plane_db.py # Control-plane DB engine/session
│   │   ├── tenant_db.py        # Per-tenant DB manager
│   │   ├── redis_client.py     # Tenant-partitioned Redis wrapper
│   │   ├── vault_client.py     # Vault abstraction (Azure + Mock)
│   │   └── qdrant_client.py    # 🆕 Qdrant vector database wrapper
│   ├── services/               # Business logic
│   │   ├── tenant_resolver.py  # TenantResolver (cache->DB->Vault)
│   │   ├── token_service.py    # JWT issuance/validation (RS256)
│   │   ├── oauth_service.py    # OAuth 2.1 flows
│   │   ├── scim_sync.py        # SCIM sync (idempotent principal_id)
│   │   ├── revocation.py       # Token/session revocation
│   │   ├── registry.py         # 🆕 Connector auto-discovery (recursive + manifest parsing)
│   │   ├── sync.py             # Blind Orchestrator (two-pass sync)
│   │   ├── indexer.py          # 🆕 Real indexer (metadata allowlist + embeddings + Qdrant)
│   │   ├── embedding.py        # 🆕 Gemini/fake embedding generation
│   │   └── cursor_store.py     # 🆕 Resume cursor storage (Drive pageToken, Gmail historyId)
│   ├── api/
│   │   ├── deps.py             # FastAPI dependencies
│   │   └── v1/
│   │       ├── auth.py         # OIDC/SSO + native email/password login
│   │       ├── oauth.py        # OAuth token/revoke endpoints
│   │       ├── me.py           # Current user info
│   │       └── admin.py        # Tenant + user provisioning
│   ├── middleware/
│   │   └── tenant_middleware.py # Tenant resolution from JWT
│   ├── connectors/             # 🆕 BLOCK B: Google connector package
│   │   └── google/
│   │       ├── manifest.yaml   # Service definitions + metadata allowlist
│   │       ├── oauth.py        # Shared OAuth manager (all Google services)
│   │       ├── watch_manager.py # Watch channel creation & renewal
│   │       ├── webhooks.py     # FastAPI webhook routes
│   │       ├── clients/
│   │       │   ├── drive_client.py  # Drive API wrapper
│   │       │   └── gmail_client.py  # Gmail API wrapper
│   │       └── services/
│   │           ├── drive_service.py # DriveConnector (implements BaseConnector)
│   │           └── gmail_service.py # GmailConnector (implements BaseConnector)
│   ├── workers/                # 🆕 BLOCK B: Celery workers
│   │   ├── celery_app.py       # Celery application config
│   │   ├── tasks.py            # Backfill + incremental sync tasks
│   │   └── beat_schedule.py    # Periodic watch renewal schedule
│   └── main.py                 # FastAPI app entrypoint
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   ├── test_signoff.py         # A1–A7 signoff tests (Block A)
│   ├── test_signoff_block_b.py # 🆕 B1–B7 signoff tests (Block B)
│   ├── fixtures/google/        # 🆕 Mock API responses (Drive + Gmail)
│   └── [other test files...]
├── scripts/
│   ├── seed_tenants.py         # Create dev tenants
│   └── run_scim_sync.py        # Manual SCIM sync trigger
├── docker-compose.yml          # 🆕 Updated: Qdrant, Celery worker, Celery beat
├── Dockerfile
├── pyproject.toml              # 🆕 Updated: Block B dependencies
├── requirements.txt            # 🆕 Updated: Block B dependencies
├── .env.example                # 🆕 Updated: Block B environment variables
├── README.md                   # This file
├── BLOCK_B_GUIDE.md            # 🆕 Complete Block B guide & testing instructions
└── SIGNOFF_BLOCK_B.md          # 🆕 Block B signoff report template
```

---

## 🚀 Quick Start

### Block A: Tenancy & Auth (Docker Only - Recommended)

**Test Block A in 5 minutes without setting up Python locally.**

```powershell
cd C:\Users\prath\OneDrive\Desktop\SnyQ_Phase_2\backend

# 1. Generate JWT keys (first time only)
mkdir -p keys
docker run --rm -v ${PWD}/keys:/keys python:3.12-slim sh -c "
    pip install cryptography && 
    python -c 'from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization; from cryptography.hazmat.backends import default_backend; private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend()); pem_private = private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()); pem_public = private_key.public_key().public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo); open(\"/keys/private.pem\", \"wb\").write(pem_private); open(\"/keys/public.pem\", \"wb\").write(pem_public); print(\"✓ JWT keys generated\")'
"

# 2. Run everything (build, setup, seed, test)
.\test-block-a.bat
```

**See also:**
- `QUICKSTART_DOCKER.md` - Detailed Docker-only guide
- `TESTING_GUIDE.md` - Comprehensive testing documentation

### Block B: Google Connector with Push Ingestion 🆕

**Test Block B (mock data) or connect your real Gmail/Drive:**

#### Option 1: Test with Mock Data (Quick)
```powershell
# Run B1-B7 signoff tests (no real Google APIs)
pytest tests/test_signoff_block_b.py -v

# Expected output: 10 tests pass (B1-B7 for Drive + Gmail)
```

#### Option 2: Connect Your Real Gmail & Drive
```powershell
# See BLOCK_B_GUIDE.md for complete step-by-step instructions:
# 1. Create Google Cloud project
# 2. Enable Drive + Gmail APIs
# 3. Create OAuth credentials
# 4. Set up Pub/Sub for Gmail push
# 5. Configure .env with your credentials
# 6. Run backfill with your account
# 7. Test live incremental updates

# Quick link:
code BLOCK_B_GUIDE.md
```

**Documentation:**
- **`BLOCK_B_GUIDE.md`** ⭐ - Complete guide: architecture, how it works, testing with real data
- **`SIGNOFF_BLOCK_B.md`** - B1-B7 signoff report template

---

## What's New in Block B

### 1. Push-Based Ingestion (No Polling!)
```
User edits Google Doc
    ↓
Google sends webhook notification (< 1 second)
    ↓
Celery task fetches ONLY the changed document
    ↓
Document searchable in ~2 seconds total
```

### 2. One Google Package, Multiple Services
```python
# Adding Calendar support later is just:
# 1. Add calendar scope to manifest.yaml
# 2. Create services/calendar_service.py
# 3. Create clients/calendar_client.py
# That's it! No changes to core files.
```

### 3. Automatic Watch Renewal
```
Celery Beat runs every 24 hours
    ↓
Checks for watches expiring in next 48 hours
    ↓
Renews them automatically
    ↓
Continuous monitoring maintained
```

### 4. Real Vector Search with Qdrant
```python
# Documents are:
# 1. Transformed to UnifiedDocument
# 2. Embedded with Gemini (or fake for testing)
# 3. Indexed to Qdrant vector database
# 4. Searchable with semantic similarity
```

---

## How to Add a Third Google Service (e.g., Calendar)

Block B is designed for easy extension. Adding Calendar requires:

1. **Update `manifest.yaml`**:
   ```yaml
   oauth_scopes:
     - https://www.googleapis.com/auth/calendar.readonly
   services:
     google_calendar:
       display_name: "Google Calendar"
       allowed_metadata_keys:
         - event_type
         - attendees
         - location
   ```

2. **Create `clients/calendar_client.py`**:
   ```python
   class CalendarClient:
       async def list_events(self, access_token, ...): ...
   ```

3. **Create `services/calendar_service.py`**:
   ```python
   class CalendarConnector(BaseConnector):
       def get_source_type(self) -> str:
           return "google_calendar"
       ...
   ```

**That's it!** No changes to:
- `sync.py` (blind orchestrator)
- `indexer.py` (uses registry)
- `registry.py` (auto-discovers)
- OAuth flow (shared manager)

---

## Setup (Alternative Methods)

### Prerequisites

- Python 3.12+
- Docker & Docker Compose

### Quick Setup (Recommended)

**Linux/Mac:**
```bash
cd backend
chmod +x setup.sh
./setup.sh
```

**Windows:**
```cmd
cd backend
setup.bat
```

See **[INSTALL.md](INSTALL.md)** for detailed installation options (Poetry, pip, Docker-only).

### Start the Application

**Quick Start:**
```bash
./run.sh       # Linux/Mac
run.bat        # Windows
```

**Or manually:**
```bash
docker-compose up -d
uvicorn app.main:app --reload
```

Visit:
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

---

## Complete Setup Instructions

For detailed setup instructions with multiple installation methods, see:
- **[INSTALL.md](INSTALL.md)** — Comprehensive installation guide (4 methods)
- **[QUICKSTART.md](QUICKSTART.md)** — Quick 2-minute setup guide
- **[BUILD_SUMMARY.md](BUILD_SUMMARY.md)** — Build details and metrics

---

## Setup (Legacy Instructions)

### 1. Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Poetry (or pip)

### 2. Clone and Install

**Option A: Using Poetry (Recommended)**
```bash
cd backend
poetry install
```

**Option B: Using pip + requirements.txt**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For development/testing
```

### 3. Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key variables:
- `CONTROL_PLANE_DATABASE_URL` — Control-plane DB (for `tenants` table)
- `REDIS_URL` — Redis connection string
- `VAULT_URL` — Leave blank for dev (uses `MockVaultClient`)
- `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` — RSA keys (auto-generated if missing)

### 4. Start Services

```bash
docker-compose up -d
```

This starts:
- **postgres**: Control-plane + tenant databases
- **redis**: Session store and per-tenant cache
- **app**: FastAPI backend (port 8000)

### 5. Seed Development Tenants

```bash
poetry run python scripts/seed_tenants.py
```

Creates 3 dev tenants: `alpha`, `beta`, `gamma`.

---

## Running the Application

### Development Mode

**With Poetry:**
```bash
poetry run uvicorn app.main:app --reload
```

**With pip/venv:**
```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
uvicorn app.main:app --reload
```

Visit:
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### Production Mode (Docker)

```bash
docker-compose up --build
```

---

## Running Tests

### All Tests

```bash
poetry run pytest
```

### Signoff Tests Only (A1–A7)

**With Poetry:**
```bash
poetry run pytest tests/test_signoff.py -v
```

**With pip/venv:**
```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
pytest tests/test_signoff.py -v
```

**Critical**: Block A signoff requires **all A1–A7 tests to PASS**.

---

## Signoff Criteria (A1–A7)

| ID | Criterion | Pass Threshold |
|----|-----------|---------------|
| **A1** | Tenant binding integrity | 100% of 100 tokens contain exactly one `tenant_id` claim and pass validation |
| **A2** | Revocation latency | 100% of revoked tokens rejected within ≤60s |
| **A3** | SCIM idempotency | `principal_id` identical across 3 sync runs, 0 drift |
| **A4** | Cross-tenant replay rejection | 50/50 cross-tenant token attempts rejected, 0 leaks |
| **A5** | Scope enforcement | 100% of requests with missing scope return 403 |
| **A6** | Secret pointer (Vault) | `db_secret_key` is a Vault key name, 0 passwords in tenant row |
| **A7** | Per-tenant cache isolation | Cache keys structurally partitioned as `tenant:{tenant_id}:*` |

**Block signoff: PASS only if A1–A7 all PASS.**

See `tests/test_signoff.py` for full test implementations.

---

## API Endpoints

### Auth

- `GET /api/v1/auth/login` — Redirect to OIDC provider
- `GET /api/v1/auth/callback` — OIDC callback, issue JWT

### OAuth

- `POST /api/v1/oauth/token` — Token endpoint (authorization_code, refresh_token, client_credentials)
- `POST /api/v1/oauth/revoke` — Revoke token/session

### User

- `GET /api/v1/me` — Current principal info from JWT

### Admin (Dev/Test)

- `POST /api/v1/admin/tenants` — Provision a new tenant

---

## Adding a New Connector (Block B)

**This is the key design goal**: adding connector #11 requires **zero edits** to core files.

1. Create a new folder under `app/connectors/` (e.g., `app/connectors/google_drive/`)
2. Implement `BaseConnector`:
   - `get_source_type() -> str`
   - `get_valid_token() -> str`
   - `fetch_delta(since, cursor) -> DeltaResult`
   - `fetch_deleted_ids(since, cursor) -> DeletionResult`
   - `transform(raw_documents) -> List[UnifiedDocument]`
3. The `ConnectorRegistry` auto-discovers your connector via reflection
4. The `SyncOrchestrator` calls your connector without ever importing it by name

**That's it.** No changes to `sync.py`, `indexer.py`, or any core file.

---

## Architecture Highlights

### 1. Tenant Resolution Flow

```
JWT (tenant_id claim)
    ↓
TenantResolver.resolve(tenant_id)
    ↓
1. Check Redis cache (tenant:{tenant_id}:routing)
2. On miss: query tenants table (control-plane DB)
3. Fetch db_password from Vault using tenant.db_secret_key
4. Cache routing (TTL 30-60 min)
5. Return TenantRouting(db_host, db_name, db_user, db_password, config)
    ↓
TenantDatabaseManager.get_session(routing...)
    ↓
Per-tenant async database session
```

### 2. Token Flow (RS256)

```
1. Issue JWT:
   - tenant_id (exactly one)
   - principal_id
   - scopes
   - jti (unique token ID)
   - exp, iat

2. Validate JWT:
   - Verify RS256 signature
   - Check expiry
   - Check revocation (Redis set: tenant:{tenant_id}:revoked:{jti})

3. Revoke JWT:
   - Mark refresh token as revoked in DB
   - Add jti to Redis revoked set
   - Publish revocation event (Redis pub/sub)
```

### 3. SCIM Sync Flow

```
1. Fetch users/groups from IdP (SCIM 2.0)
2. For each user:
   - principal_id = uuid5(NAMESPACE, idp_subject)  # Deterministic!
   - Upsert user in tenant DB
3. For each group:
   - Diff membership
   - Increment sync_version only if membership changed
4. Commit transaction
```

---

## Non-Negotiable Rules (Recap)

1. **No hardcoded secrets** — all credentials flow through `VaultClient`
2. **`tenants` table never stores passwords** — only Vault key names (A6)
3. **Per-tenant cache partitioning** — never a shared cache (A7)
4. **Every JWT has exactly one `tenant_id`** (A1, A4)
5. **`sync.py` / `indexer.py` never import specific connectors** — blind orchestrator pattern
6. **No `if tenant_id == "x"` special-casing** — the resolver is fully generic
7. **Deletion pass before delta pass** — `sync.py` two-pass design

---

## Troubleshooting

### Port Conflicts

If port 5432 or 6379 is already in use:

```bash
# Stop existing services
docker-compose down

# Or change ports in docker-compose.yml
```

### Missing RSA Keys

Keys are auto-generated on first run. To generate manually:

```bash
mkdir -p keys
ssh-keygen -t rsa -b 2048 -m PEM -f keys/private.pem -N ""
ssh-keygen -f keys/private.pem -e -m PKCS8 > keys/public.pem
```

### Alembic Migrations

```bash
# Generate migration
poetry run alembic revision --autogenerate -m "description"

# Apply migrations (per-tenant!)
poetry run alembic upgrade head
```

---

## Next Steps (Block B and Beyond)

After Block A passes signoff (A1–A7):

1. **Block B**: Connector Framework — implement real connectors (Google Drive, Slack, etc.)
2. **Block C**: Normalization & ACL Compiler — canonical document schema, identity resolution
3. **Block D**: Storage Substrate — backup/restore, KMS encryption
4. **Block E**: Chunking & Embedding Pipeline
5. **Block F**: Lexical Search Service (OpenSearch/Elasticsearch)
6. **Block G**: Vector Search Service
7. **Block H**: Knowledge Graph Service
8. ... (see architecture doc for full build order)

---

## Contributing

- All code must pass `pytest` with A1–A7 signoff tests green
- Follow Black formatting (`poetry run black app/ tests/`)
- Type hints required (`mypy` clean)
- No new dependencies without justification

---

## License

Proprietary — SnyQ Platform

---

## Contact

For questions or issues, contact the SnyQ engineering team.
