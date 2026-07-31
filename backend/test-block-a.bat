@echo off
REM One-command Block A test runner
REM This script does EVERYTHING: setup, seed, and test

echo ================================================
echo SnyQ Backend - Block A Complete Test Suite
echo ================================================
echo.

cd /d %~dp0..

REM Step 1: Build test image
echo [1/5] Building test image...
docker-compose -f docker-compose.dev.yml build test
if errorlevel 1 (
    echo ❌ Build failed
    exit /b 1
)
echo ✓ Build complete
echo.

REM Step 2: Start infrastructure
echo [2/5] Starting PostgreSQL and Redis...
docker-compose -f docker-compose.dev.yml up -d postgres redis
if errorlevel 1 (
    echo ❌ Failed to start services
    exit /b 1
)
echo ✓ Services started
echo.

REM Step 3: Wait for health checks
echo [3/5] Waiting for services to be healthy...
timeout /t 10 /nobreak >nul
echo ✓ Services ready
echo.

REM Step 4: Initialize database
echo [4/5] Initializing database and seeding tenants...
docker-compose -f docker-compose.dev.yml run --rm test alembic upgrade head
if errorlevel 1 (
    echo ❌ Migration failed
    exit /b 1
)
docker-compose -f docker-compose.dev.yml run --rm test python scripts/seed_tenants.py
if errorlevel 1 (
    echo ❌ Seeding failed
    exit /b 1
)
echo ✓ Database ready
echo.

REM Step 5: Run signoff tests
echo [5/5] Running Block A Signoff Tests (A1-A7)...
echo.
docker-compose -f docker-compose.dev.yml run --rm test pytest tests/test_signoff.py -v --tb=short
set TEST_RESULT=%errorlevel%

echo.
echo ================================================
if %TEST_RESULT% equ 0 (
    echo ✅ ALL TESTS PASSED - Block A is ready!
    echo.
    echo Next steps:
    echo 1. Review SIGNOFF.md and fill in the report
    echo 2. Start the app: docker-compose -f docker-compose.dev.yml up app
    echo 3. Access API docs: http://localhost:8000/docs
) else (
    echo ❌ SOME TESTS FAILED - Review output above
    echo.
    echo Troubleshooting:
    echo 1. Check logs: docker-compose -f docker-compose.dev.yml logs
    echo 2. See TESTING_GUIDE.md for detailed debugging
)
echo ================================================

exit /b %TEST_RESULT%
