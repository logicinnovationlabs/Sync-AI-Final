#!/usr/bin/env pwsh
# Test runner for SnyQ Phase 2 Backend
# Run all tests or specific blocks

param(
    [string]$Block = "all",
    [switch]$Verbose,
    [switch]$Coverage
)

Write-Host "================================" -ForegroundColor Cyan
Write-Host "SnyQ Phase 2 - Test Runner" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check if in backend directory
if (-not (Test-Path "tests/conftest.py")) {
    Write-Host "ERROR: Please run this script from the backend/ directory" -ForegroundColor Red
    exit 1
}

# Build pytest command
$pytestArgs = @()
if ($Verbose) {
    $pytestArgs += "-v"
}
if ($Coverage) {
    $pytestArgs += "--cov=app"
    $pytestArgs += "--cov-report=html"
    $pytestArgs += "--cov-report=term"
}

# Select tests based on block
switch ($Block.ToLower()) {
    "all" {
        Write-Host "Running ALL tests (Blocks A-L)..." -ForegroundColor Yellow
        $testPath = "tests/"
    }
    "a-j" {
        Write-Host "Running Blocks A-J tests..." -ForegroundColor Yellow
        $testPath = "tests/test_signoff.py"
    }
    "k" {
        Write-Host "Running Block K (Document Reader) tests..." -ForegroundColor Yellow
        $testPath = "tests/test_block_k.py"
    }
    "l" {
        Write-Host "Running Block L (Assistant) tests..." -ForegroundColor Yellow
        $testPath = "tests/test_block_l.py"
    }
    "k-l" {
        Write-Host "Running Blocks K & L tests..." -ForegroundColor Yellow
        $pytestArgs += "tests/test_block_k.py"
        $pytestArgs += "tests/test_block_l.py"
        $testPath = $null
    }
    "f" {
        Write-Host "Running Block F (Lexical Search) tests..." -ForegroundColor Yellow
        $testPath = "tests/test_signoff.py::test_block_f"
    }
    "g" {
        Write-Host "Running Block G (Vector Search) tests..." -ForegroundColor Yellow
        $testPath = "tests/test_signoff.py::test_block_g"
    }
    "i" {
        Write-Host "Running Block I (Signals) tests..." -ForegroundColor Yellow
        $testPath = "tests/test_signoff.py::test_block_i"
    }
    default {
        Write-Host "ERROR: Unknown block '$Block'" -ForegroundColor Red
        Write-Host ""
        Write-Host "Usage:" -ForegroundColor Yellow
        Write-Host "  .\run_tests.ps1                    # Run all tests" -ForegroundColor White
        Write-Host "  .\run_tests.ps1 -Block a-j         # Run Blocks A-J" -ForegroundColor White
        Write-Host "  .\run_tests.ps1 -Block k           # Run Block K only" -ForegroundColor White
        Write-Host "  .\run_tests.ps1 -Block l           # Run Block L only" -ForegroundColor White
        Write-Host "  .\run_tests.ps1 -Block k-l         # Run Blocks K & L" -ForegroundColor White
        Write-Host "  .\run_tests.ps1 -Block f           # Run Block F only" -ForegroundColor White
        Write-Host "  .\run_tests.ps1 -Verbose           # Verbose output" -ForegroundColor White
        Write-Host "  .\run_tests.ps1 -Coverage          # With coverage report" -ForegroundColor White
        exit 1
    }
}

# Add test path if set
if ($testPath) {
    $pytestArgs += $testPath
}

# Run pytest
Write-Host ""
Write-Host "Running: pytest $($pytestArgs -join ' ')" -ForegroundColor Gray
Write-Host ""

pytest @pytestArgs

$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "================================" -ForegroundColor Green
    Write-Host "All tests passed!" -ForegroundColor Green
    Write-Host "================================" -ForegroundColor Green
} else {
    Write-Host "================================" -ForegroundColor Red
    Write-Host "Some tests failed!" -ForegroundColor Red
    Write-Host "================================" -ForegroundColor Red
}

if ($Coverage) {
    Write-Host ""
    Write-Host "Coverage report generated at: htmlcov/index.html" -ForegroundColor Cyan
}

exit $exitCode
