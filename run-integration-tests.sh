#!/bin/bash
# Quick start script for real data integration testing

set -e

echo "=========================================="
echo "Real Data Integration Testing - Blocks A-J"
echo "=========================================="
echo ""

# Step 1: Clean previous state
echo "[Step 1/6] Cleaning previous Docker state..."
docker-compose down -v 2>/dev/null || true
echo "✓ Clean complete"
echo ""

# Step 2: Build and start services
echo "[Step 2/6] Building and starting all services..."
echo "  This may take 2-3 minutes on first run..."
docker-compose build --quiet
docker-compose up -d
echo "✓ Services started"
echo ""

# Step 3: Wait for services to be healthy
echo "[Step 3/6] Waiting for services to be healthy..."
echo "  Checking Postgres..."
timeout 60 bash -c 'until docker-compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; do sleep 2; done' || { echo "✗ Postgres failed to start"; exit 1; }
echo "  Checking Neo4j..."
sleep 30  # Neo4j takes longer
echo "  Checking Redis..."
timeout 30 bash -c 'until docker-compose exec -T redis redis-cli ping >/dev/null 2>&1; do sleep 2; done' || { echo "✗ Redis failed to start"; exit 1; }
echo "✓ All services healthy"
echo ""

# Step 4: Run migrations and seed tenants
echo "[Step 4/6] Running migrations and seeding development tenants..."
docker-compose logs migrate | tail -5
docker-compose logs seed | tail -5
echo "✓ Migrations and tenant seeding complete"
echo ""

# Step 5: Seed test data
echo "[Step 5/6] Seeding test data for Blocks D-J..."
docker-compose --profile test up seed_test_data
echo "✓ Test data seeded"
echo ""

# Step 6: Run tests
echo "[Step 6/6] Running integration tests..."
echo ""
cd backend
pytest tests/test_block_d_signoff.py \
       tests/test_block_e_signoff.py \
       tests/test_block_f_signoff.py \
       tests/test_block_g_signoff.py \
       tests/test_block_h_signoff.py \
       tests/test_block_i_signoff.py \
       tests/test_block_j_signoff.py \
       -v \
       -c pytest-real.ini

echo ""
echo "=========================================="
echo "✓ Integration testing complete!"
echo "=========================================="
echo ""
echo "Service URLs:"
echo "  • API: http://localhost:8000/docs"
echo "  • Neo4j: http://localhost:7474"
echo "  • MinIO: http://localhost:9001"
echo ""
echo "To stop services: docker-compose down"
echo "To clean all data: docker-compose down -v"
