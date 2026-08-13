@echo off
REM ============================================================
REM run-signoff-tests.bat
REM One-click signoff test runner for Windows
REM ============================================================
REM Usage: Double-click or run from PowerShell/CMD in project root
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo   SnyQ Phase 2 - Full Block A-J Signoff Test Suite
echo ============================================================
echo.

REM Check Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running. Please start Docker Desktop first.
    pause
    exit /b 1
)

echo [1/4] Building Docker images...
docker-compose -f docker-compose.signoff.yml build
if %errorlevel% neq 0 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo [2/4] Starting infrastructure and seeding real data...
docker-compose -f docker-compose.signoff.yml up -d postgres redis vault qdrant opensearch minio redpanda
timeout /t 15 /nobreak >nul

docker-compose -f docker-compose.signoff.yml run --rm migrate
if %errorlevel% neq 0 (
    echo [ERROR] Migration failed.
    pause
    exit /b 1
)

docker-compose -f docker-compose.signoff.yml run --rm seed
if %errorlevel% neq 0 (
    echo [ERROR] Seeding failed.
    pause
    exit /b 1
)

echo.
echo [3/4] Starting app and running ALL signoff tests...
docker-compose -f docker-compose.signoff.yml up app --wait
docker-compose -f docker-compose.signoff.yml run --rm ^
  -e PYTEST_ARGS="" ^
  test-runner ^
  pytest tests/ --tb=short -v --timeout=300 --ignore=tests/smoke_google_refresh_token.py -p no:cacheprovider --junitxml=/app/test-results/signoff-results.xml

set TEST_EXIT=%errorlevel%

echo.
echo [4/4] Collecting results...
echo.
if exist "test-results\signoff-results.xml" (
    echo [OK] Results saved to: test-results\signoff-results.xml
) else (
    echo [WARN] No XML results file found.
)

if %TEST_EXIT% equ 0 (
    echo.
    echo ============================================================
    echo   ALL SIGNOFF TESTS PASSED - EXIT CODE: 0
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo   SOME TESTS FAILED - EXIT CODE: %TEST_EXIT%
    echo ============================================================
)

echo.
echo To clean up containers: docker-compose -f docker-compose.signoff.yml down -v
echo.
pause
exit /b %TEST_EXIT%
