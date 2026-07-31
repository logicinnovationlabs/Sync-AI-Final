#!/bin/bash
# Quick run script - starts the app after setup
# Usage: ./run.sh

set -e

echo "Starting SnyQ Backend..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Check if Docker services are running
if ! docker-compose ps | grep -q "Up"; then
    echo "Starting Docker services..."
    docker-compose up -d
    echo "Waiting for services to be ready..."
    sleep 5
fi

# Check if keys exist
if [ ! -f "keys/private.pem" ]; then
    echo "Generating JWT keys..."
    python scripts/generate_keys.py
fi

# Start the FastAPI app
echo "Starting FastAPI application..."
echo ""
echo "================================================"
echo "SnyQ Backend is running!"
echo "================================================"
echo ""
echo "API Docs: http://localhost:8000/docs"
echo "Health:   http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop"
echo "================================================"
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
