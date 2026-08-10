# SnyQ Phase 2 Backend - Blocks A + B + C

**Version:** 0.3.0  
**Build:** Block A (Tenancy, Identity, Auth) + Block B (Google Connector + Push Ingestion) + Block C (Normalization, Identity Resolution, ACL)

---

## Overview

This is the Python backend foundation for a Glean-like enterprise knowledge platform, implementing:

- **Block A** (Tenancy, Identity, Auth) - Multi-tenant auth with OIDC/SSO and native email/password
- **Block B** (Google Connector Package) - Push-based ingestion for Google Drive & Gmail with Celery workers
- **Block C** (Normalization, Identity Resolution, ACL) - Text extraction, identity resolution, materialized ACL compilation

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

### Block B (Google Connector + Push Ingestion)
- **Celery** (Redis broker) for async task processing
- **google-api-python-client** for Drive & Gmail APIs
- **Qdrant** vector database for document embeddings
- **google-generativeai** (Gemini) for embeddings
- **Push notifications** via Drive watch channels & Gmail Pub/Sub
- **Docker Compose** with Qdrant, Celery worker, Celery beat

### Block C (Normalization, Identity Resolution, ACL) 🆕
- **python-magic** for MIME type detection (magic bytes)
- **pdfplumber**, **python-docx**, **openpyxl**, **python-pptx** for text extraction
- **pytesseract** (Pillow) for OCR fallback
- **beautifulsoup4** for HTML text extraction
- **Materialized ACL compilation** with container inheritance and group expansion
- **Identity resolution** (tenant-scoped, email-based with username fallback)
- **Cycle-safe** container and group traversal

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

## Block C: Normalization, Identity Resolution, and ACL 🆕

**Integrates between Block B's connector output and the indexer, adding:**

1. **Text Extraction** — MIME-aware extraction with OCR fallback, bounded by size/time limits
2. **Identity Resolution** — Merges identities across sources (Drive + Gmail) within a tenant, never globally
3. **ACL Compilation** — Materializes permissions (direct + inherited + group-expanded) for query-time filtering
4. **Container Inheritance** — Cycle-safe folder hierarchy traversal
5. **Group Expansion** — Cycle-safe group membership resolution

### Adding a Real Normalizer for a Future Source (e.g., Outlook)

When you add an Outlook connector (not built yet), add its normalizer:

1. **Create `app/normalizer/strategies/outlook.py`**:
   ```python
   class OutlookNormalizer(NormalizerStrategy):
       def get_source_type(self) -> str:
           return "outlook"
       
       async def extract_text(self, raw):
           # Outlook-specific text extraction
           ...
   ```

2. **Register in `app/normalizer/strategies/__init__.py`**:
   ```python
   from app.normalizer.strategies.outlook import OutlookNormalizer
   normalizer_registry.register("outlook", OutlookNormalizer)
   ```

**That's it!** No changes to `Pipeline`, `IdentityResolver`, or `ACLCompiler` — they're source-agnostic by design.

### Block C Signoff Criteria (C1–C9)

| ID | Criterion | Pass Threshold |
|----|-----------|---------------|
| **C1** | Determinism | Byte-identical CanonicalDocument across 3 runs (excluding updated_at) |
| **C2** | ACL fidelity | 100% agreement with acl_matrix.json expectations |
| **C3** | Revocation propagation | ACL updates within ≤15 min |
| **C4** | Identity resolution accuracy | ≥95% correct merges, 0 false merges (25-hint fixture) |
| **C5** | Container cycle safety | No hang, cycle logged, no incorrect inheritance |
| **C6** | Group membership cycle safety | Terminates correctly, no duplicate entries |
| **C7** | MIME spoofing detection | mime_mismatch=True, logged at WARNING, processed without crash |
| **C8** | Oversized content bounding | Truncated/bounded, not crashed, completes in bounded time |
| **C9** | Concurrent identity resolution race | Exactly one Principal row, both callers get same ID |

**Block signoff: PASS only if C1–C9 all PASS.**

Run signoff tests:
```bash
pytest tests/test_signoff_block_c.py -v
```

## Next Steps (Beyond Block C)

After Blocks A, B, and C pass signoff:

1. **Block D**: Storage Substrate — backup/restore, KMS encryption
2. **Block E**: Chunking & Embedding Pipeline (extended)
3. **Block F**: Lexical Search Service (OpenSearch/Elasticsearch) — see `services/block-f-lexical-search/`
4. **Block G**: Vector Search Service — see `services/block-g-vector-search/`
5. **Block H**: Knowledge Graph Service — see `services/block-h-graph/`
6. ... (see architecture doc for full build order)

---

## Contributing

- All code must pass `pytest` with A1–A7 signoff tests green
- Follow Black formatting (`poetry run black app/ tests/`)
- Type hints required (`mypy` clean)
- No new dependencies without justification

---

## Block C — Normalization, Identity Resolution & ACL Compilation

> **Status:** ✅ All signoff tests passing (C1–C9 + ADV-1 to ADV-16)

Block C is the security and enrichment layer that sits between **Block B's** raw connector output and the indexer. Every document passes through it before a single byte reaches the search index.

---

### What Block C Does (in 30 seconds)

```
Raw document (JSON from Drive/Gmail connector)
    ↓  ① MIME detection  (magic bytes — never trust the source)
    ↓  ② Text extraction (PDF / DOCX / HTML / OCR — hard bounded)
    ↓  ③ Identity resolution  (email → stable principal_id per tenant)
    ↓  ④ ACL compilation (direct + inherited folders + expanded groups)
    ↓  ⑤ Persist CanonicalDocument + ACLEntry rows (REPLACE, not append)
    ↓
CanonicalDocument + UnifiedDocument (ready for Qdrant indexer)
```

---

### Block C Components

```
app/
├── services/pipeline.py           # Orchestrator (MAX_EXTRACTED_CHARS guard)
├── normalizer/
│   ├── base.py                    # NormalizerStrategy ABC
│   ├── registry.py                # Strategy lookup (source_type → class)
│   ├── mime_detector.py           # Magic-byte MIME detection
│   ├── text_extractor.py          # Multi-format extractor (hard bounded)
│   ├── ocr.py                     # Tesseract OCR (fake impl for tests)
│   └── strategies/
│       ├── google_drive.py        # Drive: permissions + metadata mapping
│       ├── google_gmail.py        # Gmail: mailbox ownership model
│       └── generic.py             # Fallback for unknown sources
├── identity/
│   ├── resolver.py                # Email-first resolver, race-safe creation
│   └── matchers/
│       ├── email_matcher.py       # Case-insensitive, tenant-scoped lookup
│       └── username_matcher.py    # Fallback for sources without email
├── acl/
│   ├── compiler.py                # Direct + inherited + group expansion
│   ├── container_service.py       # Cycle-safe ancestor traversal + cache
│   └── inheritance.py             # Deny-override distance algorithm
└── storage/
    └── canonical_repo.py          # Repository (in-memory for tests; SQLAlchemy for prod)
```

**Adding a new connector source** requires only:
1. Create `app/normalizer/strategies/outlook.py`
2. Register it in `strategies/__init__.py`
3. Zero changes to `Pipeline`, `IdentityResolver`, or `ACLCompiler`.

---

### Security Controls — In Detail

#### ① MIME Spoofing Detection

**Threat:** A user uploads an `.exe` renamed as `report.txt`. Drive faithfully reports `mimeType: "text/plain"`.

**Control:** `mime_detector.detect_mime(raw_bytes, stated_mime)` reads the file's **magic bytes** via `python-magic` (libmagic) and cross-checks against the source-stated type.

```
Source claims:    "text/plain"
Magic bytes show: "application/x-executable"
Result:           mime_mismatch = True  ← logged at WARNING, persisted on CanonicalDocument
```

- Documents are **not dropped** on mismatch — user content must not silently disappear.
- Only *material* mismatches flag: `text/plain` → `application/zip|exe` is dangerous; `text/plain` → `text/x-c` (source code) is benign.
- The `mime_mismatch` field is queryable for downstream trust/safety review.

---

#### ② Content Bounding (DoS Prevention)

**Threat:** A 500 MB Google Doc exported as plain text exhausts worker memory and blocks Celery queues.

**Control — two independent hard limits:**

| Layer | Location | What it does |
|---|---|---|
| `TextExtractor` | `text_extractor.py:96–100` | Truncates extracted text at `max_chars` (default 500 000) |
| `Pipeline` | `pipeline.py` after `strategy.extract_text()` | **Second backstop** — catches strategies that bypass TextExtractor |

```python
MAX_EXTRACTED_CHARS = 500_000   # pipeline.py

content = await strategy.extract_text(raw)
if len(content) > MAX_EXTRACTED_CHARS:      # second backstop
    content = content[:MAX_EXTRACTED_CHARS]
```

Two layers mean no single strategy implementation can accidentally bypass the limit.

---

#### ③ Identity Resolution — Tenant-Scoped, Race-Safe

**Threat:** The same person appears in Drive (email), Gmail (email), and Slack (username). Without dedup, the same person has 3+ `principal_id` values, breaking ACL filtering.

**Resolution ladder** (`IdentityResolver.resolve`):
```
1. Normalize email: lowercase + strip + validate (email-validator library)
2. DB lookup: get_principal_by_email(normalized, tenant_id)  ← exact, tenant-scoped
3. Found     → update source_identities mapping, return existing principal_id
4. Not found + email present → create new Principal (race-safe, see below)
5. Not found + no email      → username matcher (source-scoped, 0.8 confidence)
6. No match at all           → raise ValueError  (no orphaned principals)
```

**Race condition handling:**
```
Task A: resolve("alice@corp.com") → not found → creates Principal
Task B: resolve("alice@corp.com") → not found → tries to create
                                               ↓
                           DB unique constraint (tenant_id, lower(email)) fires
                                               ↓
Task B catches IntegrityError → re-queries → gets Task A's winner → same principal_id
```

**Cross-tenant isolation:** `alice@corp.com` in tenant A and tenant B are **always** distinct `principal_id` values. The DB key is `(tenant_id, lower(email))` — never global.

**Email normalization:** Lowercase + strip whitespace only. No Gmail dot-folding (`alice.smith` ≠ `alicesmith`) because that would incorrectly merge identities on non-Gmail sources.

---

#### ④ ACL Compilation — Direct + Inherited + Group Expansion

**Threat:** Drive permissions cascade through folder hierarchies and can be granted to groups with nested sub-groups. Storing only the raw Drive permission list produces incorrect ACL filtering at query time.

**`ACLCompiler.compile()` materializes permissions in four steps:**

**Step 1 — Direct entries**
Every `(IdentityHint, PermissionLevel)` pair → resolved `principal_id` or `group_id` row.

**Step 2 — Container inheritance**
Walk folder ancestors upward (`ContainerService.get_ancestors()`):
```
Document (in /Marketing/Campaigns/Q4)
    ↑  Q4 folder ACL
    ↑  Campaigns folder ACL     ← nearest ancestor wins on conflict
    ↑  Marketing folder ACL
```

**Deny-override distance algorithm** (`inheritance.py`):
- Track `deny_distance` and `allow_distance` per identity key.
- If deny at distance `d_deny ≤ d_allow` → deny wins. The allow is suppressed.
- Matches Google Drive's own semantics.

**Step 3 — Group expansion (recursive, cycle-safe)**
```
Group A (READ) → Group B → Group C → Group D → alice@corp.com
                                              ↑
                           alice gets READ via granted_via="group_membership"
```
Cycle detection via `visited: Set[UUID]` — revisited groups stop and log `WARNING`.

**Step 4 — Deny override + dedup**
- Principal with both allow and deny → deny wins, all allows removed.
- Duplicate `(document_id, principal_id)` rows → keep highest level (`OWNER > DELETE > WRITE > READ > NONE`).

**ACL replace semantics (revocation guarantee):**
```python
await canonical_repo.replace_acl_entries(doc.id, new_entries)
# Atomically DELETE old rows, INSERT new ones.
# Revoked permissions cannot linger.
```

---

### Block C Test Suite

#### Signoff Tests C1–C9 (`test_signoff_block_c.py`)

| ID | Scenario | Validates |
|---|---|---|
| C1 | Same raw doc processed twice | Idempotency / determinism |
| C2 | Drive doc with 5 different role levels | ACL role mapping fidelity |
| C3 | Permission removed on re-processing | Revocation via replace semantics |
| C4 | 25 identity hints across 3 sources | Dedup accuracy across sources |
| C5 | Folder A→B→C→A cycle | Container cycle safety |
| C6 | Group A contains B, B contains A | Group membership cycle safety |
| C7 | exe-as-text vs text-as-text | MIME spoofing detection |
| C8 | 600k char content | Content bounding at 500k |
| C9 | 10 concurrent email resolutions | Race condition → 1 principal |

#### Advanced Adversarial Tests ADV-1–16 (`test_block_c_advanced.py`)

| ID | Scenario | Property tested |
|---|---|---|
| ADV-1 | Alice in Drive (×2) + Gmail | Multi-source identity unification |
| ADV-2 | 3-level hierarchy, deny at parent | Deny overrides farther allows |
| ADV-3 | Group chain A→B→C→D→alice | 4-level deep group expansion |
| ADV-4 | Same email, tenant A and tenant B | Cross-tenant never merged |
| ADV-5 | 20 concurrent coroutines, same email | Race → exactly 1 principal |
| ADV-6 | Alice removed between two passes | Stale ACL entries are 0 |
| ADV-7 | Content at M-1, M, M+1, M+100k | Boundary bounding (4 cases) |
| ADV-8 | exe claimed as text/plain | `mime_mismatch=True` persisted |
| ADV-9 | Mixed-case email + bad email | Normalization + rejection |
| ADV-10 | Gmail subject in payload.headers | Title extraction regression |
| ADV-11 | Group deny in container chain | Group deny-override correctness |
| ADV-12 | Same raw doc, two passes | Full pipeline determinism |
| ADV-13 | Empty string + whitespace content | Zero-byte no-crash guarantee |
| ADV-14 | 60-level folder chain, depth=50 | Max-depth backstop at 50 |
| ADV-15 | `type=anyone` Drive permission | Wildcard ACL tenant-scoped |
| ADV-16 | Owner + inherited READ, dedup | Highest permission wins |

```bash
# Run all Block C tests
pytest tests/test_signoff_block_c.py tests/test_block_c_smoke.py tests/test_block_c_advanced.py -v

# Expected: 31 passed
```

---

### Block C Data Models

| Model | Key field | Purpose |
|---|---|---|
| `CanonicalDocument` | `id = f"{source_type}_{source_id}"` | Enriched queryable document (stable ID) |
| `Principal` | `(tenant_id, lower(email))` unique | Resolved individual identity |
| `Group` | `(source_type, source_id, tenant_id)` unique | Group with nested members |
| `ACLEntry` | `(document_id, principal_id\|group_id)` | Materialized permission |
| `ContainerACLEntry` | `(container_id, principal_id\|group_id, tenant_id)` | Permission on folder |
| `ContainerEdge` | `(child_id, tenant_id)` → `parent_id` | Folder parent-child relationship |

---

### Known Limitations & Roadmap

| Item | Status | Next step |
|---|---|---|
| `CanonicalRepo` is in-memory | Test-only | Wire SQLAlchemy + Block A tenant DB |
| Drive text extraction is stubbed | Placeholder | Add `drive_client.download_file()` path |
| Fake OCR in tests | Test-only | Real Tesseract works if binary in PATH |
| Redis identity cache | Not implemented | Add Redis with `IDENTITY_CACHE_TTL` |
| Proactive group sync | Not implemented | Periodic sync from Drive Groups API |
| ACL revalidation beat task | Stub | Add Drive `pageToken` tracking |

---

## License


Proprietary — SnyQ Platform


---

## Contact

For questions or issues, contact the SnyQ engineering team.
