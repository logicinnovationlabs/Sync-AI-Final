#!/usr/bin/env bash
set -e

echo "======================================================================"
echo "Running Integration Signoff Suite (Blocks A-G) against Live Docker App"
echo "======================================================================"

docker compose -f docker-compose.yml -f docker-compose.integration.yml run --rm test_runner

echo ""
echo "Integration test execution finished!"
echo "======================================================================"
