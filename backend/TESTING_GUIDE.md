# Block A Testing Guide

Complete guide for testing Block A (Tenancy, Identity, and Auth Platform) using Docker.

## Quick Start

### Prerequisites
- Docker Desktop installed and running
- Git bash or PowerShell

### 1. Generate JWT Keys

First time only - generate RSA key pairs for JWT signing:

**Windows (PowerShell):**
```powershell
cd C:\Users\prath\OneDrive\Desktop\SnyQ_Phase_2\backend

# Generate keys using Docker
docker run --rm -v ${PWD}/keys:/keys python:3.12-slim sh -c "
    pip install cryptography && 
    python -c '
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)

pem_private = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

pem_public = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

with open(\"/keys/private.pem\", \"wb\") as f:
    f.write(pem_private)
with open(\"/keys/public.pem\", \"wb\") as f:
    f.write(pem_public)

print(\"✓ JWT keys generated successfully\")
'
"
```

**Or manually create keys directory:**
```powershell
mkdir keys
# Then run the docker command above
```

### 2. Start Infrastructure

Start PostgreSQL and Redis:

```powershell
docker-compose -f docker-compose.dev.yml up -d postgres redis
```

Wait for services to be healthy (about 10 seconds):
```powershell
docker-compose -f docker-compose.dev.yml ps
```

### 3. Initialize Database & Seed Tenants

Run migrations and create test tenants:

```powershell
# Run Alembic migrations
docker-compose -f docker-compose.dev.yml run --rm test alembic upgrade head

# Seed 3 test tenants (alpha, beta, gamma)
docker-compose -f docker-compose.dev.yml run --rm test python scripts/seed_tenants.py
```

### 4. Run Block A Signoff Tests

Run all A1-A7 signoff criteria tests:

```powershell
# Using the test runner script (recommended)
.\scripts\docker-test.bat

# Or directly
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_signoff.py -v

# With coverage report
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_signoff.py -v --cov=app --cov-report=html
```

### 5. Start the Application

Start the FastAPI application:

```powershell
docker-compose -f docker-compose.dev.yml up app
```

Access the API:
- **API Docs (Swagger):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

---

## Block A Signoff Criteria

All tests are located in `tests/test_signoff.py` and implement the following criteria:

### A1: Tenant Binding Integrity
**Test:** `test_A1_tenant_binding_integrity`

Issues 100 tokens across 3 tenants (interactive + service accounts) and validates:
- Every token contains exactly one `tenant_id` claim
- All tokens pass signature validation
- All tokens pass expiry validation

**Pass Threshold:** 100% compliance

### A2: Revocation Latency
**Test:** `test_A2_revocation_latency`

Revokes an active session and polls a protected endpoint every 5 seconds:
- 20 trials
- Measures time until rejection

**Pass Threshold:** 100% of trials rejected within ≤60 seconds

### A3: SCIM Idempotency
**Test:** `test_A3_scim_idempotency`

Runs SCIM sync 3 times against an unchanged directory:
- Restarts service between runs (simulated by clearing caches)
- Verifies `principal_id` is identical across all runs
- Ensures 0 drift

**Pass Threshold:** 100% consistent `principal_id` values

### A4: Cross-Tenant Replay Rejection
**Test:** `test_A4_cross_tenant_replay_rejection`

Attempts to use Tenant A tokens to access Tenant B endpoints:
- 50 attempts
- Validates rejection with 401/403

**Pass Threshold:** 50/50 rejected, 0 leaks

### A5: Scope Enforcement
**Test:** `test_A5_scope_enforcement`

Calls every scoped endpoint with tokens missing required scopes:
- Tests all protected endpoints
- Validates standardized error envelope

**Pass Threshold:** 100% return 403 with proper error format

### A6: Secret Pointer (Vault)
**Test:** `test_A6_secret_pointer_vault`

Provisions a new tenant and inspects the `tenants` table:
- Validates `db_secret_key` contains a Vault key name (e.g., `kv/tenantA/db_password`)
- Asserts no raw passwords in the row

**Pass Threshold:** 100% use Vault key names, 0 raw passwords

### A7: Per-Tenant Cache Isolation
**Test:** `test_A7_per_tenant_cache_isolation`

Resolves Tenant A (populates cache), then attempts to read Tenant B's routing:
- Validates cache keys are partitioned (e.g., `tenant:{tenant_id}:routing`)
- Ensures Tenant B resolution never returns Tenant A's data

**Pass Threshold:** 100% cache isolation

---

## Running Individual Tests

Run specific signoff tests:

```powershell
# Run only A1
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_signoff.py::test_A1_tenant_binding_integrity -v

# Run only A2
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_signoff.py::test_A2_revocation_latency -v

# Run A1-A4
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_signoff.py -k "A1 or A2 or A3 or A4" -v
```

---

## Running Other Test Suites

```powershell
# Run all unit tests
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/ -v

# Run specific test files
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_tenant_resolver.py -v
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_token_service.py -v
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_native_auth.py -v

# Run with specific markers
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/ -v -m "not slow"
```

---

## Debugging Failed Tests

### View detailed error output
```powershell
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_signoff.py -v --tb=long
```

### Run with verbose logging
```powershell
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_signoff.py -v -s --log-cli-level=DEBUG
```

### Inspect database state
```powershell
# Connect to PostgreSQL
docker exec -it snyq_postgres_dev psql -U postgres -d control_plane

# List tenants
SELECT id, subdomain, db_host, db_port, db_name, db_secret_key FROM tenants;

# Connect to a tenant database
docker exec -it snyq_postgres_dev psql -U postgres -d tenant_alpha

# List users
SELECT principal_id, email, display_name FROM users;
```

### Inspect Redis cache
```powershell
# Connect to Redis
docker exec -it snyq_redis_dev redis-cli

# List all keys
KEYS *

# Get tenant routing
GET tenant:1:routing

# Check revocation sets
SMEMBERS revoked:tokens
SMEMBERS revoked:sessions
```

---

## Generating Signoff Report

After running tests, generate the official signoff report:

```powershell
# Run tests and capture output
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_signoff.py -v > test_output.txt

# Review SIGNOFF.md template
code SIGNOFF.md

# Fill in the results based on test_output.txt
```

---

## Cleanup

### Stop all services
```powershell
docker-compose -f docker-compose.dev.yml down
```

### Remove volumes (full reset)
```powershell
docker-compose -f docker-compose.dev.yml down -v
```

### Rebuild after code changes
```powershell
docker-compose -f docker-compose.dev.yml build test
docker-compose -f docker-compose.dev.yml build app
```

---

## Troubleshooting

### Issue: "Cannot connect to PostgreSQL"
**Solution:**
```powershell
# Check if postgres is running
docker-compose -f docker-compose.dev.yml ps postgres

# View postgres logs
docker-compose -f docker-compose.dev.yml logs postgres

# Restart postgres
docker-compose -f docker-compose.dev.yml restart postgres
```

### Issue: "JWT key not found"
**Solution:**
```powershell
# Verify keys exist
dir keys

# Should see:
# private.pem
# public.pem

# If missing, regenerate (see step 1)
```

### Issue: "Test database not initialized"
**Solution:**
```powershell
# Run migrations
docker-compose -f docker-compose.dev.yml run --rm test alembic upgrade head

# Seed tenants
docker-compose -f docker-compose.dev.yml run --rm test python scripts/seed_tenants.py
```

### Issue: "Tests are slow"
**Solution:**
```powershell
# Run in parallel (requires pytest-xdist)
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_signoff.py -v -n auto
```

---

## File Reference

| File | Purpose |
|------|---------|
| `tests/test_signoff.py` | A1-A7 signoff criteria tests |
| `tests/conftest.py` | Pytest fixtures and test configuration |
| `SIGNOFF.md` | Official signoff report template |
| `docker-compose.dev.yml` | Development Docker Compose configuration |
| `Dockerfile.dev` | Development Dockerfile with test dependencies |
| `scripts/seed_tenants.py` | Creates test tenants (alpha, beta, gamma) |
| `scripts/docker-test.bat` | Windows test runner script |

---

## Next Steps After Signoff

1. ✅ Complete all A1-A7 tests
2. ✅ Fill out `SIGNOFF.md`
3. ✅ Commit test results
4. ✅ Ready for Block B (Connector Framework) development

---

## Support

If you encounter issues:
1. Check Docker logs: `docker-compose -f docker-compose.dev.yml logs`
2. Verify environment variables in `docker-compose.dev.yml`
3. Ensure ports 5432, 6379, 8000 are not in use
4. Try a clean rebuild: `docker-compose -f docker-compose.dev.yml down -v && docker-compose -f docker-compose.dev.yml build --no-cache`
