#!/bin/sh
# Bind the HTTP port first so Render does not kill the service while Alembic
# is still trying (or failing) to reach Postgres.
set -eu
PORT="${PORT:-8000}"
uvicorn app.main:app --host 0.0.0.0 --port "$PORT" &
UV_PID=$!
python -m alembic upgrade heads || echo "WARN: alembic upgrade skipped (database unreachable)"
wait "$UV_PID"
