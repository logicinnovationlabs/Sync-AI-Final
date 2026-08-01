#!/bin/bash
# Run tests inside Docker container
# Usage: ./scripts/docker-test.sh [test-file] [pytest-args]

set -e

echo "================================================"
echo "SnyQ Backend - Docker Test Runner"
echo "================================================"

# Default test file
TEST_FILE="${1:-tests/test_signoff.py}"
shift || true
PYTEST_ARGS="${@:--v --tb=short}"

echo ""
echo "Test file: $TEST_FILE"
echo "Pytest args: $PYTEST_ARGS"
echo ""

# Build the test image
echo "Building test image..."
docker-compose -f docker-compose.dev.yml build test

echo ""
echo "Ensuring dependencies are running..."
docker-compose -f docker-compose.dev.yml up -d postgres redis

echo ""
echo "Waiting for services to be healthy..."
sleep 5

echo ""
echo "Running tests..."
docker-compose -f docker-compose.dev.yml run --rm test pytest "$TEST_FILE" $PYTEST_ARGS

echo ""
echo "================================================"
echo "Tests complete!"
echo "================================================"
