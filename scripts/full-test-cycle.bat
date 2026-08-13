@echo off
echo ======================================================================
echo Starting Full Cycle: Docker Build -> Migration -> 3-Org Seed -> Integration Tests
echo ======================================================================

call scripts\docker-up.bat

echo.
echo Running integration tests...
call scripts\run-integration-tests.bat

echo.
echo Full test cycle completed!
