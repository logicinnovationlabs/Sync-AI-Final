# SnyQ Phase 2 - Developer Setup Guide

Complete setup guide for developers joining the project. This setup is **fully isolated** and won't interfere with other Docker containers or projects you have running.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Project Structure](#project-structure)
3. [Initial Setup](#initial-setup)
4. [Running the Application](#running-the-application)
5. [Testing](#testing)
6. [Development Workflow](#development-workflow)
7. [Troubleshooting](#troubleshooting)
8. [Isolation & Safety](#isolation--safety)

---

## 🔧 Prerequisites

### Required Software

```yaml
- Git: Latest version
- Docker Desktop: 4.25+ (Windows/Mac) or Docker Engine 24+ (Linux)
- Python: 3.12+
- Node.js: 18+ (optional, for frontend)
- Visual Studio Code or Cursor IDE (recommended)
```

### System Requirements

```yaml
- RAM: Minimum 8GB (16GB recommended)
- Disk Space: 10GB free space
- OS: Windows 10/11, macOS 12+, or Linux (Ubuntu 20.04+)
```

### Verify Prerequisites

```bash
# Check Docker
docker --version
docker-compose --version

# Check Python
python --version

# Check Git
git --version
```

---

## 📁 Project Structure

```
SnyQ_Phase_2/
├── backend/                    # Main FastAPI backend
│   ├── app/                   # Application code
│   │   ├── api/              # API routes (Blocks A-J)
│   │   ├── core/             # Core config, security, deps
│   │   ├── models/           # Pydantic models
│   │   ├── services/         # Business logic (Blocks D-J)
│   │   │   ├── graph/       # Block H: Neo4j graph
│   │   │   ├── signals/     # Block I: Activity signals
│   │   │   ├── vector/      # Block G: Qdrant vectors
│   │   │   ├── lexical/     # Block F: OpenSearch
│   │   │   └── ...
│   │   ├── storage/          # Block D: Storage substrate
│   │   └── workers/          # Celery tasks
│   ├── tests/                # All test files
│   │   ├── test_block_d_signoff.py
│   │   ├── test_block_e_signoff.py
│   │   ├── ...
│   │   └── test_block_j_signoff.py
│   ├── scripts/              # Utility scripts
│   │   ├── seed_tenants.py         # Seed dev tenants
│   │   └── seed_test_data.py       # Seed integration test data
│   ├── migrations/           # Database migrations (Alembic)
│   ├── requirements.txt      # Python dependencies
│   ├── Dockerfile           # Backend container image
│   └── pytest.ini           # Pytest configuration
├── docker-compose.yml       # Main orchestration (all services)
├── .env.docker             # Docker environment variables
├── CONSOLIDATION_LOG.md    # Technical documentation
├── REAL_DATA_TESTING_GUIDE.md  # Testing guide
└── DEVELOPER_SETUP.md      # This file
```

---

## 🚀 Initial Setup

### Step 1: Clone the Repository

```bash
# Clone from your organization's Git repository
git clone <your-repo-url> SnyQ_Phase_2
cd SnyQ_Phase_2

# Checkout main/master branch
git checkout main
```

### Step 2: Configure Environment

```bash
# Copy environment template (if it exists)
cp .env.example .env.docker  # Or create from scratch

# Edit .env.docker with your settings
# All default values should work for local development
```

**Default `.env.docker` is already configured for local development. No changes needed!**

### Step 3: Generate JWT Keys

```bash
cd backend

# Create keys directory
mkdir -p keys

# Generate RSA key pair (for JWT authentication)
# Option 1: Using OpenSSL (macOS/Linux)
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem

# Option 2: Using Python script (Windows/All platforms)
python scripts/generate_keys.py

cd ..
```

### Step 4: Set Up Python Environment (Optional for IDE)

This is only needed if you want IDE autocomplete and local development. Tests can run directly.

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Windows CMD:
.\venv\Scripts\activate.bat

# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

cd ..
```

---

## 🐳 Running the Application

### Quick Start (All Services)

```bash
# Start all services in background
docker-compose up -d

# Wait for services to be healthy (~60 seconds)
# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### Service Status

After startup, you should see:

```
NAME                  STATUS
snyq_postgres         Up XX minutes (healthy)
snyq_redis            Up XX minutes (healthy)
snyq_neo4j            Up XX minutes (healthy)
snyq_opensearch       Up XX minutes
snyq_qdrant           Up XX minutes
snyq_minio            Up XX minutes
snyq_vault            Up XX minutes
snyq_redpanda         Up XX minutes
snyq_app              Up XX minutes (healthy)
snyq_celery_worker    Up XX minutes
snyq_celery_beat      Up XX minutes
```

### Access Service UIs

| Service | URL | Credentials |
|---------|-----|-------------|
| **API Documentation** | http://localhost:8000/docs | N/A |
| **API Health** | http://localhost:8000/health | N/A |
| **Neo4j Browser** | http://localhost:7474 | neo4j / password |
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin |
| **OpenSearch** | http://localhost:9200 | N/A (security disabled) |
| **Qdrant Dashboard** | http://localhost:6333/dashboard | N/A |
| **Vault UI** | http://localhost:8200/ui | Token: `root` |

### Initial Data Seeding

```bash
# Seed development tenants (alpha, beta, gamma)
# This happens automatically via docker-compose

# View seed logs
docker-compose logs seed

# Manually re-seed (if needed)
docker-compose exec app python scripts/seed_tenants.py
```

---

## 🧪 Testing

### Run All Tests (Mock Backends)

```bash
cd backend

# Activate venv (if using local Python)
.\venv\Scripts\Activate  # Windows
source venv/bin/activate  # macOS/Linux

# Run all signoff tests with mock backends (fast)
pytest tests/test_block_d_signoff.py \
       tests/test_block_e_signoff.py \
       tests/test_block_f_signoff.py \
       tests/test_block_g_signoff.py \
       tests/test_block_h_signoff.py \
       tests/test_block_i_signoff.py \
       tests/test_block_j_signoff.py \
       -v

# Expected: 26 tests passed in ~30 seconds
```

### Run Tests Against Real Backends

```bash
# Step 1: Ensure Docker services are running
docker-compose ps

# Step 2: Seed test data into Docker services
docker-compose exec app python scripts/seed_test_data.py

# Expected output:
# [OK] SEEDING BLOCK D: Storage Substrate
# [OK] SEEDING BLOCK E: Chunking
# [OK] SEEDING BLOCK F: Lexical Search
# [OK] SEEDING BLOCK G: Vector Search
# [OK] SEEDING BLOCK H: Knowledge Graph
# [OK] SEEDING BLOCK I: Activity Signals
# [OK] ALL BLOCKS SEEDED SUCCESSFULLY

# Step 3: Run tests (from backend directory)
cd backend
pytest tests/test_block_d_signoff.py \
       tests/test_block_e_signoff.py \
       tests/test_block_f_signoff.py \
       tests/test_block_g_signoff.py \
       tests/test_block_h_signoff.py \
       tests/test_block_i_signoff.py \
       tests/test_block_j_signoff.py \
       -v

# Expected: 26 tests passed in ~60 seconds
```

### Test Individual Blocks

```bash
# Test specific block
pytest tests/test_block_h_signoff.py -v -s

# Test with verbose output
pytest tests/test_block_i_signoff.py -v -s

# Run only Block H, I, J tests
pytest tests/test_block_h_signoff.py \
       tests/test_block_i_signoff.py \
       tests/test_block_j_signoff.py \
       -v
```

---

## 💻 Development Workflow

### Making Code Changes

```bash
# 1. Create a feature branch
git checkout -b feature/your-feature-name

# 2. Make your changes in backend/app/

# 3. Run tests locally
cd backend
pytest tests/ -v

# 4. If you changed Docker code, rebuild
docker-compose build app

# 5. Restart the service
docker-compose up -d app

# 6. Verify changes
curl http://localhost:8000/health
docker-compose logs app --tail 50
```

### Hot Reload (Development Mode)

To enable auto-reload on code changes:

```bash
# Stop production containers
docker-compose down

# Start with development override
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Or mount code as volume (add to docker-compose.yml):
# volumes:
#   - ./backend/app:/app/app
```

### Database Migrations

```bash
# Create a new migration
docker-compose exec app alembic revision --autogenerate -m "Description"

# Apply migrations
docker-compose exec app alembic upgrade head

# Rollback migration
docker-compose exec app alembic downgrade -1

# View migration history
docker-compose exec app alembic history
```

### Adding New Dependencies

```bash
# Add to backend/requirements.txt
cd backend
echo "new-package==1.2.3" >> requirements.txt

# Rebuild Docker image
cd ..
docker-compose build app

# Restart service
docker-compose up -d app
```

---

## 🔍 Troubleshooting

### Services Won't Start

```bash
# Check what's running
docker-compose ps

# View logs for failed service
docker-compose logs <service-name>

# Common issues:
# 1. Ports already in use
docker ps -a  # Check for conflicting containers
netstat -ano | findstr :5432  # Windows: Check port usage
lsof -i :5432  # macOS/Linux: Check port usage

# 2. Insufficient resources
# Increase Docker Desktop resources:
# Settings → Resources → Advanced
# Recommended: 8GB RAM, 4 CPUs

# 3. Stale containers
docker-compose down -v  # Remove everything
docker-compose up -d    # Fresh start
```

### Tests Failing

```bash
# 1. Ensure services are healthy
docker-compose ps

# 2. Check if data is seeded
docker-compose exec app python scripts/seed_test_data.py

# 3. Check database connectivity
docker-compose exec app python -c "from app.storage.control_plane_db import ControlPlaneSessionLocal; print('DB OK')"

# 4. View test output with more detail
cd backend
pytest tests/test_block_h_signoff.py -v -s --tb=short

# 5. Check Python dependencies
pip list | grep -E "pytest|asyncio"
```

### Container Name Conflicts

If you see "container name already in use":

```bash
# Option 1: Stop conflicting containers
docker ps -a | grep snyq_
docker rm -f snyq_redis  # Example

# Option 2: Use project-specific command
docker-compose -p snyq_phase_2 down
docker-compose -p snyq_phase_2 up -d
```

### Neo4j Takes Long to Start

```bash
# Neo4j can take 60-90 seconds on first start
# Check logs
docker-compose logs neo4j

# Wait for this message:
# "Remote interface available at http://localhost:7474/"

# Then wait another 30 seconds for health check to pass
```

### Disk Space Issues

```bash
# Clean up unused Docker resources
docker system prune -a --volumes

# Remove only this project's volumes
docker-compose down -v

# Check disk usage
docker system df
```

---

## 🛡️ Isolation & Safety

### This Project is Fully Isolated

✅ **Container Names**: All containers prefixed with `snyq_*`
```
snyq_postgres, snyq_redis, snyq_neo4j, etc.
```

✅ **Docker Network**: Project-specific network
```
snyq_phase_2_default
```

✅ **Docker Volumes**: Project-specific volumes
```
snyq_phase_2_postgres_data
snyq_phase_2_redis_data
snyq_phase_2_neo4j_data
snyq_phase_2_qdrant_data
snyq_phase_2_minio_data
```

✅ **Ports**: Exposed only to localhost (127.0.0.1)
```
localhost:5432 → Postgres
localhost:7687 → Neo4j
localhost:9200 → OpenSearch
localhost:6333 → Qdrant
localhost:8000 → API
```

### Running Alongside Other Projects

**This project will NOT interfere with:**
- Other Docker projects (different container names, networks, volumes)
- Other databases running on different ports
- Other development environments

**To avoid port conflicts:**

If you have another service on the same port, edit `docker-compose.yml`:

```yaml
# Example: Change Postgres port
postgres:
  ports:
    - "5433:5432"  # Changed from 5432:5432
```

Then update `.env.docker`:
```bash
DB_HOST=localhost
DB_PORT=5433
```

### Cleanup Options

```bash
# Stop services (keeps data)
docker-compose stop

# Stop and remove containers (keeps data)
docker-compose down

# Remove containers + networks (keeps volumes)
docker-compose down --remove-orphans

# FULL CLEANUP - removes ALL data
docker-compose down -v

# Remove only specific service data
docker volume rm snyq_phase_2_postgres_data
```

---

## 📚 Additional Resources

### Documentation Files

- **CONSOLIDATION_LOG.md** - Technical architecture and block consolidation details
- **REAL_DATA_TESTING_GUIDE.md** - Comprehensive testing guide with real backends
- **backend/README.md** - Backend-specific documentation
- **docker-compose.yml** - Service configuration

### Key Directories

- **backend/app/services/** - Business logic for Blocks D-J
- **backend/tests/** - All test suites
- **backend/scripts/** - Utility scripts (seeding, migrations)
- **backend/migrations/** - Database schema versions

### Command Cheat Sheet

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f [service-name]

# Check service status
docker-compose ps

# Restart a service
docker-compose restart [service-name]

# Run tests
cd backend && pytest tests/ -v

# Seed test data
docker-compose exec app python scripts/seed_test_data.py

# Access shell in container
docker-compose exec app bash

# Run Alembic migrations
docker-compose exec app alembic upgrade head

# Clean everything
docker-compose down -v
```

---

## 🆘 Getting Help

### Internal Support

1. **Check existing documentation** in this repository
2. **Search issue tracker** for similar problems
3. **Ask in team Slack/Discord** channel
4. **Create a GitHub issue** with:
   - Steps to reproduce
   - Error messages
   - Docker logs (`docker-compose logs`)
   - System info (OS, Docker version)

### Useful Commands for Debugging

```bash
# Full system information
docker version
docker-compose version
docker system info

# Service-specific logs
docker-compose logs postgres --tail 100
docker-compose logs app --tail 100

# Container inspection
docker inspect snyq_app
docker stats snyq_app

# Network debugging
docker network ls
docker network inspect snyq_phase_2_default

# Volume inspection
docker volume ls
docker volume inspect snyq_phase_2_postgres_data
```

---

## ✅ Setup Verification Checklist

After completing setup, verify:

- [ ] All Docker containers are running (`docker-compose ps`)
- [ ] API health check passes (`curl http://localhost:8000/health`)
- [ ] Neo4j browser accessible (http://localhost:7474)
- [ ] Development tenants created (`docker-compose logs seed`)
- [ ] All mock tests pass (`pytest tests/ -v`)
- [ ] Test data seeded successfully (`docker-compose exec app python scripts/seed_test_data.py`)
- [ ] Real backend tests pass (after seeding data)
- [ ] No port conflicts with other projects
- [ ] JWT keys generated (`backend/keys/private.pem` and `public.pem` exist)

---

## 🎉 Success!

You're now ready to develop on SnyQ Phase 2! 

**Next Steps:**
1. Explore the API at http://localhost:8000/docs
2. Review CONSOLIDATION_LOG.md for architecture details
3. Run the test suite to understand the codebase
4. Start building your feature!

**Happy Coding! 🚀**
