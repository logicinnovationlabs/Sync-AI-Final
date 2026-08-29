"""Stamp existing tenant DBs at 005, then alembic upgrade head.

Tenant databases were created with Base.metadata.create_all, not Alembic, so they
may have no alembic_version. This command stamps 005_merge_heads then upgrades so
pending migrations (006, 007, …) run against each tenant DB.

Does not print connection URLs or passwords.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

_db_url = os.getenv("CONTROL_PLANE_DATABASE_URL", "")
if "@postgres:" in _db_url:
    DB_HOST = "postgres"
else:
    DB_HOST = os.getenv("DB_HOST", "localhost")

BACKEND_ROOT = Path(__file__).resolve().parent.parent
STAMP_REVISION = "005_merge_heads"
PYTHON = sys.executable


def _tenant_sync_url(db_name: str) -> str:
    # Same superuser pattern as seed_tenants.py (dev). Do not log this URL.
    return f"postgresql://postgres:postgres@{DB_HOST}:5432/{db_name}"


def _alembic_url(db_name: str) -> str:
    user = quote_plus("postgres")
    password = quote_plus("postgres")
    return f"postgresql+asyncpg://{user}:{password}@{DB_HOST}:5432/{db_name}"


def _alembic_env(db_name: str) -> dict:
    env = os.environ.copy()
    env["CONTROL_PLANE_DATABASE_URL"] = _alembic_url(db_name)
    return env


def _run_alembic(args: list[str], db_name: str) -> None:
    result = subprocess.run(
        [PYTHON, "-m", "alembic", *args],
        cwd=str(BACKEND_ROOT),
        env=_alembic_env(db_name),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Strip anything that looks like a URL from captured output.
        err = (result.stderr or result.stdout or "").replace(_alembic_url(db_name), "[redacted]")
        raise RuntimeError(f"alembic {' '.join(args)} failed for db={db_name}: {err[-800:]}")
    for line in (result.stdout or "").splitlines():
        if "INFO" in line or "Running" in line or line.strip().endswith("head"):
            print(f"    {line.strip()}")


def _current_revision(engine) -> str | None:
    with engine.connect() as conn:
        tables = conn.execute(
            text("SELECT to_regclass('public.alembic_version')")
        ).scalar()
        if not tables:
            return None
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def migrate_one(db_name: str, subdomain: str) -> str:
    print(f"\nTenant subdomain={subdomain} db={db_name}")
    engine = create_engine(_tenant_sync_url(db_name))
    try:
        revision = _current_revision(engine)
        print(f"  alembic_version={revision or '(none)'}")

        head = subprocess.run(
            [PYTHON, "-m", "alembic", "heads"],
            cwd=str(BACKEND_ROOT),
            env=_alembic_env(db_name),
            capture_output=True,
            text=True,
        )
        head_revision = (head.stdout or "").strip().split()[0] if head.returncode == 0 else ""
        if revision and head_revision and revision == head_revision:
            print(f"  already at head ({revision}); skipping")
            return f"already-{revision}"

        # Manual Phase C DDL must not remain as the live table. Drop it when
        # Alembic has not yet created 006, then let upgrade recreate it.
        if revision not in (None, "006_pending_identity_queue", head_revision):
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS pending_identity_queue CASCADE"))
            print("  dropped pending_identity_queue (manual patch or pre-006)")

        if revision is None:
            _run_alembic(["stamp", STAMP_REVISION], db_name)
            print(f"  stamped {STAMP_REVISION}")

        _run_alembic(["upgrade", "head"], db_name)
        print("  upgrade head complete")
        return "upgraded"
    finally:
        engine.dispose()


def main() -> int:
    print("Migrating registered tenant databases to alembic head")
    cp = create_engine(_tenant_sync_url("control_plane"))
    try:
        with Session(cp) as session:
            rows = session.execute(
                text("SELECT subdomain, db_name FROM tenants ORDER BY subdomain")
            ).all()
            if not rows:
                print("No tenants registered.")
                return 1
            results = []
            for subdomain, db_name in rows:
                status = migrate_one(db_name, subdomain)
                results.append((subdomain, db_name, status))
    finally:
        cp.dispose()

    print("\nSummary:")
    for subdomain, db_name, status in results:
        print(f"  {subdomain} ({db_name}): {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
