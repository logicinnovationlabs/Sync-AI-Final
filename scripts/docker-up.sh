#!/usr/bin/env bash
set -e

echo "======================================================================"
echo "Starting SnyQ Phase 2 Docker Stack (Blocks A-G + Infrastructure)"
echo "======================================================================"

docker compose down
docker compose build
docker compose up -d postgres redis qdrant opensearch minio vault redpanda otel-collector

echo "Waiting for core infrastructure (Postgres, Redis, Vault)..."
sleep 10

echo "Running database migrations..."
docker compose run --rm migrate

echo "Seeding 3 tenant organizations (Alpha, Beta, Gamma)..."
docker compose run --rm seed

echo "Starting FastAPI Backend (app) and Celery Worker/Beat..."
docker compose up -d app celery_worker celery_beat

echo "Waiting for backend health check..."
sleep 5
docker compose ps

echo ""
echo "SnyQ Backend Stack is RUNNING!"
echo "API Docs: http://localhost:8000/docs"
echo "Health:   http://localhost:8000/health"
echo "======================================================================"
