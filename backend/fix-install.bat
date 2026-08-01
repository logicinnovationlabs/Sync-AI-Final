@echo off
REM Fix installation script - ensures all dependencies are installed correctly
echo ================================================
echo SnyQ Backend - Installation Fix
echo ================================================
echo.

cd /d %~dp0..

echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ❌ Virtual environment not found. Run setup.bat first.
    exit /b 1
)

echo.
echo [1/3] Installing core dependencies...
pip install -r requirements.txt --no-deps
if errorlevel 1 (
    echo ❌ Installation failed
    pause
    exit /b 1
)

echo.
echo [2/3] Installing missing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ Installation failed
    pause
    exit /b 1
)

echo.
echo [3/3] Verifying critical packages...
python -c "import asyncpg; import cryptography; import fastapi; import sqlalchemy; print('✓ All critical packages installed')"
if errorlevel 1 (
    echo ❌ Verification failed
    pause
    exit /b 1
)

echo.
echo ================================================
echo ✅ Installation fixed successfully!
echo ================================================
pause
