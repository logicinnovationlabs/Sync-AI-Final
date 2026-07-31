@echo off
REM Quick run script - starts the app after setup
REM Usage: run.bat

echo Starting SnyQ Backend...

REM Activate virtual environment if it exists
if exist "venv" (
    call venv\Scripts\activate.bat
)

REM Check if Docker services are running (simplified check)
docker-compose ps >nul 2>&1
if errorlevel 1 (
    echo Starting Docker services...
    docker-compose up -d
    echo Waiting for services to be ready...
    timeout /t 5 /nobreak >nul
)

REM Check if keys exist
if not exist "keys\private.pem" (
    echo Generating JWT keys...
    python scripts\generate_keys.py
)

REM Start the FastAPI app
echo Starting FastAPI application...
echo.
echo ================================================
echo SnyQ Backend is running!
echo ================================================
echo.
echo API Docs: http://localhost:8000/docs
echo Health:   http://localhost:8000/health
echo.
echo Press Ctrl+C to stop
echo ================================================
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
