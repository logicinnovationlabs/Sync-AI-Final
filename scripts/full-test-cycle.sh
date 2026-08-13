#!/usr/bin/env bash
set -e

echo "======================================================================"
echo "Starting Full Cycle: Docker Build -> Migration -> 3-Org Seed -> Integration Tests"
echo "======================================================================"

./scripts/docker-up.sh

echo ""
echo "Running integration tests..."
./scripts/run-integration-tests.sh

echo ""
echo "Full test cycle completed!"
