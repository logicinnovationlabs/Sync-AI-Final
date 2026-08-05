@echo off
REM Block C test runner for Windows
REM Runs all Block C tests in sequence

echo ============================================================
echo BLOCK C TEST SUITE
echo ============================================================
echo.

echo [1/4] Running smoke tests...
pytest tests/test_block_c_smoke.py -v
if errorlevel 1 (
    echo FAILED: Smoke tests
    exit /b 1
)
echo.

echo [2/4] Running unit tests...
pytest tests/test_mime_detector.py tests/test_text_extractor.py tests/test_normalizer_google_drive.py tests/test_normalizer_google_gmail.py tests/test_identity_resolver.py tests/test_container_service.py tests/test_acl_compiler.py -v
if errorlevel 1 (
    echo FAILED: Unit tests
    exit /b 1
)
echo.

echo [3/4] Running integration tests...
pytest tests/test_pipeline_integration.py -v
if errorlevel 1 (
    echo FAILED: Integration tests
    exit /b 1
)
echo.

echo [4/4] Running signoff tests (C1-C9)...
pytest tests/test_signoff_block_c.py -v
if errorlevel 1 (
    echo FAILED: Signoff tests
    exit /b 1
)
echo.

echo ============================================================
echo BLOCK C TEST SUITE: ALL PASSED
echo ============================================================
echo.
echo Block C is ready for signoff.
echo See SIGNOFF_BLOCK_C.md for detailed report.
