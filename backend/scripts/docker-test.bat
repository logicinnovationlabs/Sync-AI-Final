@echo off
REM Run tests inside Docker container
REM Usage: scripts\docker-test.bat [test-file] [pytest-args]

echo ================================================
echo SnyQ Backend - Docker Test Runner
echo ================================================

REM Default test file
set TEST_FILE=%1
if "%TEST_FILE%"=="" set TEST_FILE=tests/test_signoff.py

set PYTEST_ARGS=%2 %3 %4 %5 %6 %7 %8 %9
if "%PYTEST_ARGS%"=="" set PYTEST_ARGS=-v --tb=short

echo.
echo Test file: %TEST_FILE%
echo Pytest args: %PYTEST_ARGS%
echo.

REM Build the test image
echo Building test image...
docker-compose -f docker-compose.dev.yml build test

echo.
echo Ensuring dependencies are running...
docker-compose -f docker-compose.dev.yml up -d postgres redis

echo.
echo Waiting for services to be healthy...
timeout /t 5 /nobreak >nul

echo.
echo Running tests...
docker-compose -f docker-compose.dev.yml run --rm test pytest %TEST_FILE% %PYTEST_ARGS%

echo.
echo ================================================
echo Tests complete!
echo ================================================
