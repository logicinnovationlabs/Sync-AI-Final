#!/bin/sh
# Bind HTTP immediately. Migrations run in the background and cannot take the
# process down — this is what kept the API live before Alembic was in the
# foreground start command.
set -eu
PORT="${PORT:-8000}"
(python -m alembic upgrade heads || true) &
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
