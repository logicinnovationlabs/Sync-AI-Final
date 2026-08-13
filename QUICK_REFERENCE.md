# Quick Reference Card - SnyQ Phase 2

**1-page developer reference for common tasks**

---

## 🚀 Quick Start

```bash
# Clone and setup
git clone <repo-url> SnyQ_Phase_2
cd SnyQ_Phase_2
cd backend && mkdir keys && python scripts/generate_keys.py && cd ..

# Start all services
docker-compose up -d

# Seed dev data
docker-compose logs seed  # Happens automatically

# Run tests
cd backend && pytest tests/ -v
```

---

## 🐳 Docker Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose stop

# Stop and remove
docker-compose down

# Full reset (deletes data!)
docker-compose down -v

# Check status
docker-compose ps

# View logs
docker-compose logs -f [service]

# Restart service
docker-compose restart [service]

# Rebuild after code changes
docker-compose build app
docker-compose up -d app
```

---

## 🧪 Testing

```bash
cd backend

# All tests (mock backends)
pytest tests/ -v

# Specific block
pytest tests/test_block_h_signoff.py -v -s

# Real backends (seed first!)
docker-compose exec app python scripts/seed_test_data.py
pytest tests/test_block_*_signoff.py -v
```

---

## 🌐 Service URLs

| Service | URL | Login |
|---------|-----|-------|
| API Docs | http://localhost:8000/docs | - |
| Neo4j | http://localhost:7474 | neo4j/password |
| MinIO | http://localhost:9001 | minioadmin/minioadmin |
| OpenSearch | http://localhost:9200 | - |
| Qdrant | http://localhost:6333/dashboard | - |

---

## 🔧 Common Tasks

### Make Code Changes
```bash
# Edit code in backend/app/
docker-compose build app
docker-compose up -d app
docker-compose logs app
```

### Database Migration
```bash
docker-compose exec app alembic revision -m "description"
docker-compose exec app alembic upgrade head
```

### Add Python Package
```bash
# Add to backend/requirements.txt
docker-compose build app
docker-compose up -d app
```

### Shell Access
```bash
docker-compose exec app bash
docker-compose exec postgres psql -U postgres
```

### Reseed Data
```bash
docker-compose exec app python scripts/seed_tenants.py
docker-compose exec app python scripts/seed_test_data.py
```

---

## 🛡️ Isolation

✅ Container names: `snyq_*` (won't conflict)  
✅ Network: `snyq_phase_2_default`  
✅ Volumes: `snyq_phase_2_*`  
✅ Ports: localhost only

**Safe to run alongside other Docker projects!**

---

## 🔥 Troubleshooting

### Services won't start
```bash
docker-compose down -v
docker-compose up -d
docker-compose logs [service]
```

### Port already in use
```bash
# Edit docker-compose.yml ports section
# Change "5432:5432" to "5433:5432"
```

### Tests failing
```bash
docker-compose ps  # Check all healthy
docker-compose exec app python scripts/seed_test_data.py
cd backend && pytest tests/ -v -s --tb=short
```

### Container name conflict
```bash
docker rm -f snyq_redis  # Example
docker-compose up -d
```

### Neo4j slow to start
```bash
# Wait 60-90 seconds after docker-compose up
docker-compose logs neo4j
# Look for: "Remote interface available"
```

---

## 📁 Project Structure

```
backend/
├── app/
│   ├── api/v1/         # API routes
│   ├── services/       # Blocks D-J logic
│   │   ├── graph/     # Block H: Neo4j
│   │   ├── signals/   # Block I: Postgres
│   │   ├── vector/    # Block G: Qdrant
│   │   └── lexical/   # Block F: OpenSearch
│   ├── storage/        # Block D: Storage
│   └── workers/        # Celery tasks
├── tests/              # Test suites
│   └── test_block_*_signoff.py
└── scripts/            # Utility scripts
```

---

## 📚 Documentation

- **DEVELOPER_SETUP.md** - Full setup guide (you are here)
- **CONSOLIDATION_LOG.md** - Architecture details
- **REAL_DATA_TESTING_GUIDE.md** - Testing guide
- **http://localhost:8000/docs** - API documentation

---

## ✅ Health Check

```bash
# All services running?
docker-compose ps

# API healthy?
curl http://localhost:8000/health

# Tests passing?
cd backend && pytest tests/ -v --tb=line

# Data seeded?
docker-compose logs seed
docker-compose exec app python scripts/seed_test_data.py
```

---

## 🎯 Expected Results

**After setup:**
- 11 containers running (postgres, neo4j, redis, app, etc.)
- API responds at localhost:8000
- 26 tests pass (Blocks D-J)
- Dev tenants: alpha, beta, gamma

**Test execution time:**
- Mock backends: ~30 seconds
- Real backends: ~60 seconds

---

## 🆘 Help

1. Read DEVELOPER_SETUP.md (full guide)
2. Check GitHub issues
3. Ask in team chat
4. Include: `docker-compose logs` + error message

---

**Quick Tip:** Bookmark this page and http://localhost:8000/docs for fast reference! 🚀
