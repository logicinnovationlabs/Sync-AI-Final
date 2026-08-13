# Real Data Integration Testing Guide - Blocks A to J

Complete step-by-step guide for testing all blocks (A-J) with real backends in Docker.

## Prerequisites

- Docker and Docker Compose installed
- All code changes committed (optional but recommended)
- At least 8GB RAM available for Docker

## Step-by-Step Instructions

### Step 1: Clean Previous Docker State (Optional)

If you've run Docker before, clean up old containers and volumes:

```bash
docker-compose down -v
docker volume prune -f
```

### Step 2: Build and Start All Services

Start all backend services (Postgres, Redis, Neo4j, OpenSearch, Qdrant, MinIO, Vault, etc.):

```bash
# Build images (first time or after code changes)
docker-compose build

# Start all services
docker-compose up -d

# Check that all services are healthy
docker-compose ps
```

Wait for all services to be healthy (this may take 2-3 minutes). You should see:
- ✅ postgres (healthy)
- ✅ neo4j (healthy)
- ✅ redis (healthy)
- ✅ opensearch (started)
- ✅ qdrant (started)
- ✅ minio (started)
- ✅ vault (started)

**Verify with logs:**
```bash
# Watch all logs
docker-compose logs -f

# Or check specific services
docker-compose logs neo4j
docker-compose logs opensearch
```

### Step 3: Run Database Migrations

Migrations should run automatically via the `migrate` service, but verify:

```bash
docker-compose logs migrate
```

You should see: `[OK] Migrations completed successfully`

### Step 4: Seed Development Tenants

This creates 3 test tenants (alpha, beta, gamma):

```bash
docker-compose logs seed
```

You should see: `[OK] SEEDING COMPLETE - Created 3 development tenants`

### Step 5: Seed Test Data for Integration Tests

This seeds realistic test data into all backends for Blocks D-J:

```bash
# Run the test data seeder
docker-compose --profile test up seed_test_data

# Or manually inside backend container
docker-compose exec app python scripts/seed_test_data.py
```

**Expected output:**
```
============================================================
COMPREHENSIVE DATA SEEDING FOR BLOCKS D-J
============================================================
Test Tenant: test-integration

SEEDING BLOCK D: Storage Substrate
[OK] Created test tenant: test-integration
[OK] Seeded 4 secrets in Vault
[OK] Seeded 3 test files in MinIO

SEEDING BLOCK E: Chunking
[OK] Seeded 3 documents for chunking

SEEDING BLOCK F: Lexical Search
[OK] Indexed 3 documents in OpenSearch

SEEDING BLOCK G: Vector Search
[OK] Indexed 3 vectors in Qdrant

SEEDING BLOCK H: Knowledge Graph
[OK] Created 3 person nodes, 3 document nodes
[OK] Created 6 relationships

SEEDING BLOCK I: Activity Signals
[OK] Ingested 14 activity events

============================================================
[OK] ALL BLOCKS SEEDED SUCCESSFULLY
============================================================
```

### Step 6: Run Tests Against Real Backends

Now run all signoff tests (A-J) against real backends:

**Option A: Run all tests together**
```bash
cd backend

# Run all Block D-J tests with real backends
pytest tests/test_block_d_signoff.py \
       tests/test_block_e_signoff.py \
       tests/test_block_f_signoff.py \
       tests/test_block_g_signoff.py \
       tests/test_block_h_signoff.py \
       tests/test_block_i_signoff.py \
       tests/test_block_j_signoff.py \
       -v -s \
       -c pytest-real.ini
```

**Option B: Run tests by block**
```bash
cd backend

# Test Block D (Storage)
pytest tests/test_block_d_signoff.py -v -s -c pytest-real.ini

# Test Block E (Chunking)
pytest tests/test_block_e_signoff.py -v -s -c pytest-real.ini

# Test Block F (Lexical Search)
pytest tests/test_block_f_signoff.py -v -s -c pytest-real.ini

# Test Block G (Vector Search)
pytest tests/test_block_g_signoff.py -v -s -c pytest-real.ini

# Test Block H (Knowledge Graph)
pytest tests/test_block_h_signoff.py -v -s -c pytest-real.ini

# Test Block I (Activity Signals)
pytest tests/test_block_i_signoff.py -v -s -c pytest-real.ini

# Test Block J (Query Federator)
pytest tests/test_block_j_signoff.py -v -s -c pytest-real.ini
```

**Option C: Run tests inside Docker container**
```bash
# Run tests in the app container
docker-compose exec app pytest tests/test_block_d_signoff.py \
                              tests/test_block_e_signoff.py \
                              tests/test_block_f_signoff.py \
                              tests/test_block_g_signoff.py \
                              tests/test_block_h_signoff.py \
                              tests/test_block_i_signoff.py \
                              tests/test_block_j_signoff.py \
                              -v -s
```

### Step 7: Verify Results

**Expected output:**
```
===================== test session starts =====================
collected 26 items

Block D Tests (4 tests)
tests/test_block_d_signoff.py::test_d1_provisioning_time PASSED
tests/test_block_d_signoff.py::test_d2_backup_restore_integrity PASSED
tests/test_block_d_signoff.py::test_d3_encryption_at_rest PASSED
tests/test_block_d_signoff.py::test_d4_key_rotation_zero_downtime PASSED

Block E Tests (4 tests)
tests/test_block_e_signoff.py::test_e1_chunk_integrity PASSED
tests/test_block_e_signoff.py::test_e2_throughput PASSED
tests/test_block_e_signoff.py::test_e3_reembed_trigger PASSED
tests/test_block_e_signoff.py::test_e4_idempotency PASSED

Block F Tests (4 tests)
tests/test_block_f_signoff.py::test_f1_index_lag PASSED
tests/test_block_f_signoff.py::test_f2_latency PASSED
tests/test_block_f_signoff.py::test_f3_facet_accuracy PASSED
tests/test_block_f_signoff.py::test_f4_acl_enforcement PASSED

Block G Tests (4 tests)
tests/test_block_g_signoff.py::test_g1_recall_at_10 PASSED
tests/test_block_g_signoff.py::test_g2_latency PASSED
tests/test_block_g_signoff.py::test_g3_model_version_isolation PASSED
tests/test_block_g_signoff.py::test_g4_acl_prefilter PASSED

Block H Tests (3 tests)
tests/test_block_h_signoff.py::test_h1_edge_fidelity PASSED
tests/test_block_h_signoff.py::test_h2_traversal_latency PASSED
tests/test_block_h_signoff.py::test_h3_merge_split_integrity PASSED

Block I Tests (3 tests)
tests/test_block_i_signoff.py::test_i1_privacy_threshold PASSED
tests/test_block_i_signoff.py::test_i2_retention_enforcement PASSED
tests/test_block_i_signoff.py::test_i3_signal_freshness PASSED

Block J Tests (4 tests)
tests/test_block_j_signoff.py::test_j1_latency_p95 PASSED
tests/test_block_j_signoff.py::test_j2_redteam_zero_unauthorized PASSED
tests/test_block_j_signoff.py::test_j3_ndcg_at_10 PASSED
tests/test_block_j_signoff.py::test_j4_graceful_degradation PASSED

=================== 26 passed in XX.XXs ===================
```

### Step 8: Access Service UIs (Optional)

You can access various service dashboards:

- **App API**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474 (neo4j / password)
- **MinIO Console**: http://localhost:9001 (minioadmin / minioadmin)
- **OpenSearch**: http://localhost:9200
- **Qdrant Dashboard**: http://localhost:6333/dashboard

### Step 9: View Seeded Data

**Check Neo4j Graph:**
```bash
# Access Neo4j browser at http://localhost:7474
# Run query: MATCH (n) RETURN n LIMIT 25
```

**Check OpenSearch Indices:**
```bash
curl http://localhost:9200/_cat/indices
curl http://localhost:9200/test-integration/_search?pretty
```

**Check Qdrant Collections:**
```bash
curl http://localhost:6333/collections
```

**Check Postgres Data:**
```bash
docker-compose exec postgres psql -U postgres -d control_plane -c "SELECT * FROM tenants;"
```

### Step 10: Cleanup

When done testing, stop and clean up:

```bash
# Stop all services
docker-compose down

# Remove all volumes (WARNING: deletes all data)
docker-compose down -v

# Remove images (optional)
docker-compose down --rmi all
```

## Troubleshooting

### Services not starting
```bash
# Check logs for specific service
docker-compose logs <service-name>

# Restart a specific service
docker-compose restart <service-name>

# Rebuild if code changed
docker-compose build <service-name>
docker-compose up -d <service-name>
```

### Neo4j connection refused
```bash
# Wait for Neo4j to fully start (can take 30-60 seconds)
docker-compose logs neo4j

# Check if it's healthy
docker-compose ps neo4j
```

### Tests failing with connection errors
```bash
# Make sure all services are up
docker-compose ps

# Check if ports are accessible
curl http://localhost:9200  # OpenSearch
curl http://localhost:6333  # Qdrant
curl http://localhost:7474  # Neo4j
```

### Seed script errors
```bash
# Check if migrations ran
docker-compose logs migrate

# Check if tenants were seeded
docker-compose logs seed

# Run seed manually with verbose output
docker-compose exec app python scripts/seed_test_data.py
```

## Quick Reference

```bash
# Full workflow (clean slate)
docker-compose down -v
docker-compose build
docker-compose up -d
docker-compose --profile test up seed_test_data
cd backend && pytest tests/test_block_*_signoff.py -v -c pytest-real.ini

# Re-seed data only
docker-compose exec app python scripts/seed_test_data.py

# Run specific block tests
cd backend && pytest tests/test_block_h_signoff.py -v -s -c pytest-real.ini

# View all logs
docker-compose logs -f

# Stop everything
docker-compose down
```

## Success Criteria

✅ All 26 tests pass (D1-D4, E1-E4, F1-F4, G1-G4, H1-H3, I1-I3, J1-J4)
✅ Tests complete in < 2 minutes
✅ No connection errors to any backend service
✅ Data is properly seeded in all services (verified via service UIs)

## Next Steps After Successful Testing

1. Document any performance findings
2. Update CONSOLIDATION_LOG.md with real backend test results
3. Create production deployment plan
4. Set up CI/CD pipeline for automated testing
