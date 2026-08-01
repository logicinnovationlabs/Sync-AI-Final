@echo off
REM Quick fix script for installation issues
echo ================================================
echo SnyQ Backend - Quick Installation Fix
echo ================================================
echo.

cd /d %~dp0

echo Checking virtual environment...
if not exist "venv" (
    echo ❌ Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

echo ✓ Virtual environment found
echo.

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo [1/5] Uninstalling conflicting packages...
pip uninstall pydantic pydantic-core pydantic-settings -y

echo.
echo [2/5] Installing core dependencies...
pip install -r requirements.txt

echo.
echo [3/5] Verifying installation...
python -c "import asyncpg; import cryptography; import fastapi; import sqlalchemy; print('✓ All critical packages installed')"
if errorlevel 1 (
    echo ❌ Verification failed - some packages missing
    echo.
    echo Try full reinstall:
    echo 1. Delete venv folder
    echo 2. Run setup.bat again
    pause
    exit /b 1
)

echo.
echo [4/5] Generating JWT keys...
if not exist "keys\private.pem" (
    python scripts\generate_keys.py
    if errorlevel 1 (
        echo ❌ Key generation failed
        pause
        exit /b 1
    )
    echo ✓ JWT keys generated
) else (
    echo ✓ JWT keys already exist
)

echo.
echo [5/5] Checking Docker containers...
docker ps >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Docker is not running. Start Docker Desktop and run:
    echo    docker-compose up -d
) else (
    echo ✓ Docker is running
    echo.
    echo Starting PostgreSQL and Redis...
    docker-compose up -d postgres redis
    timeout /t 5 /nobreak >nul
    echo ✓ Services started
)

echo.
echo ================================================
echo ✅ Installation Fixed!
echo ================================================
echo.
echo Next steps:
echo 1. Seed tenants:   python scripts\seed_tenants.py
echo 2. Run tests:      pytest tests\test_signoff.py -v
echo 3. Start app:      uvicorn app.main:app --reload
echo.
echo Or use Docker instead: .\test-block-a.bat
echo ================================================
pause
