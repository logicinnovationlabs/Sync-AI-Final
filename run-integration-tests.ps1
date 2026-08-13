# PowerShell script for Windows - Real Data Integration Testing

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Real Data Integration Testing - Blocks A-J" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Clean previous state
Write-Host "[Step 1/6] Cleaning previous Docker state..." -ForegroundColor Yellow
docker-compose down -v 2>$null
Write-Host "[OK] Clean complete" -ForegroundColor Green
Write-Host ""

# Step 2: Build and start services
Write-Host "[Step 2/6] Building and starting all services..." -ForegroundColor Yellow
Write-Host "  This may take 2-3 minutes on first run..." -ForegroundColor Gray
docker-compose build --quiet
docker-compose up -d
Write-Host "[OK] Services started" -ForegroundColor Green
Write-Host ""

# Step 3: Wait for services
Write-Host "[Step 3/6] Waiting for services to be healthy..." -ForegroundColor Yellow
Write-Host "  Waiting for Postgres..." -ForegroundColor Gray
Start-Sleep -Seconds 10
Write-Host "  Waiting for Neo4j..." -ForegroundColor Gray
Start-Sleep -Seconds 30
Write-Host "  Waiting for OpenSearch..." -ForegroundColor Gray
Start-Sleep -Seconds 10
Write-Host "[OK] All services should be healthy" -ForegroundColor Green
Write-Host ""

# Step 4: Check migrations and seed
Write-Host "[Step 4/6] Checking migrations and tenant seeding..." -ForegroundColor Yellow
docker-compose logs migrate --tail 5
docker-compose logs seed --tail 5
Write-Host "[OK] Migrations and tenant seeding complete" -ForegroundColor Green
Write-Host ""

# Step 5: Seed test data
Write-Host "[Step 5/6] Seeding test data for Blocks D-J..." -ForegroundColor Yellow
docker-compose --profile test up seed_test_data
Write-Host "[OK] Test data seeded" -ForegroundColor Green
Write-Host ""

# Step 6: Run tests
Write-Host "[Step 6/6] Running integration tests..." -ForegroundColor Yellow
Write-Host ""
Set-Location backend
pytest tests/test_block_d_signoff.py `
       tests/test_block_e_signoff.py `
       tests/test_block_f_signoff.py `
       tests/test_block_g_signoff.py `
       tests/test_block_h_signoff.py `
       tests/test_block_i_signoff.py `
       tests/test_block_j_signoff.py `
       -v `
       -c pytest-real.ini

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "[OK] Integration testing complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Service URLs:"
Write-Host "  • API: http://localhost:8000/docs"
Write-Host "  • Neo4j: http://localhost:7474"
Write-Host "  • MinIO: http://localhost:9001"
Write-Host ""
Write-Host "To stop services: docker-compose down"
Write-Host "To clean all data: docker-compose down -v"
