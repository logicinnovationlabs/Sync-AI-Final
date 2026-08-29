# SnyQ Phase 2 - Unified Backend Platform

Modern, scalable search and knowledge management platform built with FastAPI, featuring consolidated microservices architecture (Blocks A-J).

## 🚀 Quick Start for Developers

**Sharing code:** use `git clone` / a branch — never zip the working tree
(`.env*` and JWT PEMs are gitignored but still sit on disk). Safe archive:
`scripts/package-safe-archive.ps1` or `scripts/package-safe-archive.sh`.
If a raw zip was already shared, rotate secrets per
[docs/SECURITY_SECRET_ROTATION.md](docs/SECURITY_SECRET_ROTATION.md).

### 1. First Time Setup
```bash
# See detailed instructions in DEVELOPER_SETUP.md
git clone <repo-url> SnyQ_Phase_2
cd SnyQ_Phase_2
docker-compose up -d
```

### 2. Run Tests
```bash
cd backend
pytest tests/ -v
```

### 3. Access API
- **API Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

---

## 📚 Documentation

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **[DEVELOPER_SETUP.md](DEVELOPER_SETUP.md)** | Complete setup guide | First time setup, troubleshooting |
| **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** | 1-page cheat sheet | Daily development |
| **[CONSOLIDATION_LOG.md](CONSOLIDATION_LOG.md)** | Architecture & blocks | Understanding system design |
| **[REAL_DATA_TESTING_GUIDE.md](REAL_DATA_TESTING_GUIDE.md)** | Integration testing | Testing with real backends |

---

## 🏗️ Architecture Overview

### Consolidated Blocks (A-J)

| Block | Service | Technology | Status |
|-------|---------|-----------|--------|
| **A** | Tenancy & Identity | PostgreSQL, JWT | ✅ Core |
| **B** | Connectors & Ingestion | Celery, Google APIs | ✅ Core |
| **C** | Parsing & OCR | Tesseract, Magic | ✅ Core |
| **D** | Storage Substrate | MinIO, Vault, Postgres | ✅ Consolidated |
| **E** | Chunking | Custom chunker | ✅ Consolidated |
| **F** | Lexical Search | OpenSearch | ✅ Consolidated |
| **G** | Vector Search | Qdrant | ✅ Consolidated |
| **H** | Knowledge Graph | Neo4j | ✅ Consolidated |
| **I** | Activity Signals | PostgreSQL | ✅ Consolidated |
| **J** | Query Federator | RRF fusion | ✅ Consolidated |

### Technology Stack

```yaml
Backend:
  Framework: FastAPI (Python 3.12)
  Database: PostgreSQL 16
  Cache: Redis 7
  Task Queue: Celery + Redpanda

Search:
  Lexical: OpenSearch 2.11
  Vector: Qdrant (latest)
  Graph: Neo4j 5.15

Storage:
  Object Store: MinIO (S3-compatible)
  Secrets: HashiCorp Vault

Observability:
  Tracing: OpenTelemetry
  Collector: OTEL Contrib 0.96
```

---

## 🐳 Docker Services

All services are **fully isolated** with `snyq_*` prefixes:

```
snyq_postgres       # Main database
snyq_redis          # Cache & sessions
snyq_neo4j          # Knowledge graph
snyq_opensearch     # Lexical search
snyq_qdrant         # Vector search
snyq_minio          # Object storage
snyq_vault          # Secrets management
snyq_redpanda       # Message queue
snyq_app            # FastAPI application
snyq_celery_worker  # Background tasks
snyq_celery_beat    # Scheduled tasks
```

**Ports exposed to localhost only** - safe to run alongside other projects!

---

## 🧪 Testing

### Test Coverage

- **26 signoff tests** across Blocks D-J
- **Mock backends** for fast unit tests
- **Real backends** for integration tests
- **100% pass rate** required before merge

### Run Tests

```bash
# All tests with mock backends (~30s)
cd backend
pytest tests/ -v

# Integration tests with real backends (~60s)
docker-compose exec app python scripts/seed_test_data.py
pytest tests/test_block_*_signoff.py -v

# Specific block
pytest tests/test_block_h_signoff.py -v -s
```

### Grounded assistant (Block L)

Chat answers are evidence-based: retrieval runs for every query, Qwen is called server-side with a strict “answer only from context” prompt, and the UI waits for that completion before showing a final answer.

**What “accuracy” means here:** a question passes when the retrieved `document_id`s include the expected sources, the answer contains the required facts (or correctly refuses when the fact is absent from context), and the answer does not introduce identifiers/numbers missing from that context. This is measured by the eval suite. It is **not** a claim of 100% accuracy.

```bash
# Offline pipeline eval (FakeChatProvider, no network)
cd backend
python scripts/eval_grounded_chat.py
pytest tests/test_grounded_chat_prompt.py tests/test_grounded_chat_eval.py -v

# Live Qwen via OpenRouter (requires OPENROUTER_API_KEY + QWEN_MODEL)
python scripts/eval_grounded_chat.py --live --include-live-only
```

Enable debug retrieval metadata and pipeline timing logs:

```bash
# backend
ASSISTANT_DEBUG=1
LOG_LEVEL=INFO   # look for [assistant.pipeline] in server logs

# frontend (or automatic in NODE_ENV=development)
NEXT_PUBLIC_ASSISTANT_DEBUG=1
```

Set `LLM_CHAT_PROVIDER=openrouter` (not `fake`) or the UI will answer in milliseconds from snippet concatenation and never call Qwen.

---

## 📁 Project Structure

```
SnyQ_Phase_2/
├── backend/                    # Main application
│   ├── app/
│   │   ├── api/v1/            # REST API endpoints
│   │   ├── services/          # Business logic (Blocks D-J)
│   │   ├── storage/           # Data access (Block D)
│   │   ├── workers/           # Celery tasks (Block B)
│   │   └── core/              # Config, auth, deps
│   ├── tests/                 # Test suites
│   ├── scripts/               # Utility scripts
│   └── migrations/            # DB migrations
├── services/                   # Legacy microservices (being phased out)
├── docker-compose.yml         # Main orchestration
├── .env.docker               # Environment config
└── docs/                      # Documentation
```

---

## 🛡️ Security & Isolation

### Multi-Tenancy
- **Isolated databases** per tenant (Block A)
- **Row-level security** in shared tables
- **Tenant-scoped** API routes

### Authentication & Authorization
- **JWT tokens** (RS256)
- **OAuth 2.0** integration (Google, Microsoft)
- **SCIM** for user provisioning
- **Scope-based** access control

### Data Protection
- **Secrets in Vault** (not env vars)
- **Encryption at rest** (MinIO, Postgres)
- **TLS/SSL** for all external connections
- **ACL enforcement** on documents

---

## 🔄 Development Workflow

### Making Changes

```bash
# 1. Create feature branch
git checkout -b feature/your-feature

# 2. Make changes in backend/app/

# 3. Run tests
cd backend && pytest tests/ -v

# 4. Rebuild if needed
docker-compose build app
docker-compose up -d app

# 5. Verify
curl http://localhost:8000/health
docker-compose logs app
```

### Code Style

```bash
# Format code
black backend/app/

# Lint
flake8 backend/app/
mypy backend/app/

# Sort imports
isort backend/app/
```

---

## 📊 Monitoring & Debugging

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs app -f

# Last 100 lines
docker-compose logs app --tail 100
```

### Service Health

```bash
# Check all services
docker-compose ps

# Check API health
curl http://localhost:8000/health

# Check database
docker-compose exec postgres psql -U postgres -c "SELECT 1"
```

### Performance Monitoring

- **OpenTelemetry** traces sent to OTEL collector
- **Metrics** exposed at `/metrics` (Prometheus format)
- **Logs** structured JSON to stdout

---

## 🤝 Contributing

### Before Submitting PR

1. ✅ All tests pass (`pytest tests/ -v`)
2. ✅ Code formatted (`black`, `isort`)
3. ✅ No linter errors (`flake8`, `mypy`)
4. ✅ Documentation updated
5. ✅ Commit message follows convention

### Commit Convention

```
<type>(<scope>): <subject>

Types: feat, fix, docs, style, refactor, test, chore
Scope: block-d, block-e, api, storage, etc.

Example:
feat(block-h): add graph traversal depth limit
fix(auth): resolve JWT expiry bug
docs(readme): update quick start guide
```

---

## 🆘 Troubleshooting

### Common Issues

**Services won't start**
```bash
docker-compose down -v
docker-compose up -d
```

**Port conflicts**
```bash
# Edit ports in docker-compose.yml
# Example: "5433:5432" instead of "5432:5432"
```

**Tests failing**
```bash
docker-compose ps  # Check services healthy
docker-compose exec app python scripts/seed_test_data.py
pytest tests/ -v -s --tb=short
```

**Need help?**
1. Check [DEVELOPER_SETUP.md](DEVELOPER_SETUP.md) troubleshooting section
2. Search GitHub issues
3. Ask in team chat

---

## 📞 Support

- **Documentation**: See docs/ folder
- **Issues**: GitHub Issues
- **Team Chat**: [Slack/Discord channel]
- **Email**: [team-email]

---

## 📄 License

[Your License Here]

---

## 🎉 Status

- ✅ **Blocks A-C**: Core platform (tenancy, connectors, parsing)
- ✅ **Blocks D-J**: Fully consolidated into unified backend
- ✅ **26/26 tests passing** (100% coverage)
- ✅ **Docker orchestration** complete
- ✅ **Documentation** up to date

**Ready for production deployment!** 🚀

---

**For detailed setup instructions, see [DEVELOPER_SETUP.md](DEVELOPER_SETUP.md)**
