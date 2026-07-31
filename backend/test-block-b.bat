@echo off
REM One-click Block B instant test runner
echo ================================================
echo SnyQ Backend - Block B Signoff Test Suite
echo ================================================
echo.

cd /d %~dp0

if exist venv\Scripts\python.exe (
    echo [1/1] Running Block B Signoff Tests using venv...
    echo.
    .\venv\Scripts\python.exe -m pytest tests/test_signoff_block_b.py -v --tb=short
) else (
    echo ⚠️ Virtualenv not found. Falling back to system pytest...
    pytest tests/test_signoff_block_b.py -v --tb=short
)

set TEST_RESULT=%errorlevel%

echo.
echo ================================================
if %TEST_RESULT% equ 0 (
    echo ✅ ALL 10 BLOCK B TESTS PASSED (PASS thresholds B1-B7)!
) else (
    echo ❌ SOME TESTS FAILED
)
echo ================================================

exit /b %TEST_RESULT%
