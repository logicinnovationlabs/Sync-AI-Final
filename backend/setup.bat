@echo off
REM Quick setup script for SnyQ Backend (Block A) - Windows
REM Usage: setup.bat

echo ================================================
echo SnyQ Backend - Block A Setup
echo ================================================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.12+
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo ✓ Found Python %PYTHON_VERSION%

REM Create virtual environment
if not exist "venv" (
    echo.
    echo Creating virtual environment...
    python -m venv venv
    echo ✓ Virtual environment created
) else (
    echo ✓ Virtual environment already exists
)

REM Activate virtual environment
echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo.
echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
echo ✓ Dependencies installed

REM Ask about dev dependencies
echo.
set /p INSTALL_DEV="Install development dependencies? (y/n): "
if /i "%INSTALL_DEV%"=="y" (
    pip install -r requirements-dev.txt
    echo ✓ Development dependencies installed
)

REM Generate JWT keys
echo.
echo Generating JWT keys...
if not exist "keys\private.pem" (
    python scripts\generate_keys.py
    echo ✓ JWT keys generated
) else (
    echo ✓ JWT keys already exist
)

REM Copy .env.example if .env doesn't exist
echo.
if not exist ".env" (
    copy .env.example .env
    echo ✓ Created .env file from .env.example
    echo ⚠️  Please edit .env with your configuration
) else (
    echo ✓ .env file already exists
)

echo.
echo ================================================
echo ✅ Setup Complete!
echo ================================================
echo.
echo Next steps:
echo 1. Start services: docker-compose up -d
echo 2. Seed tenants:   python scripts\seed_tenants.py
echo 3. Run tests:      pytest tests\test_signoff.py -v
echo 4. Start app:      uvicorn app.main:app --reload
echo.
echo API Docs: http://localhost:8000/docs
echo ================================================

pause
