"""
Connectivity check against the real Supabase project DB (R5).

Prefers settings.supabase_db_url / SUPABASE_DB_URL.
Refuses to treat a localhost/local-Docker URL as Supabase evidence.

Never prints connection strings or credentials — only host class,
success/failure, Postgres version, and RLS/bypass role flags.

Usage (from backend/):
  python scripts/check_supabase_connectivity.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402


def _to_asyncpg(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def _ensure_ssl(url: str) -> str:
    """Supabase pooler/direct usually requires TLS; add ssl=require if absent."""
    normalized = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(normalized)
    qs = parse_qs(parsed.query)
    if "ssl" not in qs and "sslmode" not in qs:
        qs["ssl"] = ["require"]
    new_query = urlencode({k: v[0] for k, v in qs.items()})
    rebuilt = parsed._replace(query=new_query)
    return _to_asyncpg(urlunparse(rebuilt))


def _host_class(url: str) -> tuple[str, str, int, str]:
    normalized = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(normalized)
    host = parsed.hostname or "?"
    port = parsed.port or 5432
    db = (parsed.path or "/").lstrip("/") or "?"
    localish = host in ("localhost", "127.0.0.1", "postgres") or host.endswith(".local")
    cls = "LOCAL_STANDIN" if localish else "NON_LOCAL"
    if "supabase" in host.lower():
        cls = "SUPABASE_CLOUD"
    return cls, host, port, db


async def main() -> int:
    url = settings.supabase_db_url or os.getenv("SUPABASE_DB_URL")
    print(f"backend_dot_env_file: {'PRESENT' if (ROOT / '.env').exists() else 'MISSING'}")
    print(f"supabase_db_url_setting: {'PRESENT' if settings.supabase_db_url else 'MISSING'}")
    print(f"SUPABASE_DB_URL_env: {'PRESENT' if os.getenv('SUPABASE_DB_URL') else 'MISSING'}")

    if not url:
        print("connectivity: BLOCKED")
        print("reason: SUPABASE_DB_URL / settings.supabase_db_url not set")
        print("r5: refusing to fall back to local control_plane_database_url")
        return 2

    host_class, host, port, db = _host_class(url)
    # Print host class + redacted endpoint (hostname only — needed to prove non-local)
    print(f"target_host_class: {host_class}")
    print(f"target_endpoint: {host}:{port}/{db}")

    if host_class == "LOCAL_STANDIN":
        print("connectivity: BLOCKED")
        print("reason: SUPABASE_DB_URL points at a local stand-in (R5)")
        return 2

    async_url = _ensure_ssl(_to_asyncpg(url))
    engine = create_async_engine(async_url, echo=False)
    try:
        async with engine.connect() as conn:
            one = (await conn.execute(text("SELECT 1"))).scalar_one()
            version = (await conn.execute(text("SELECT version()"))).scalar_one()
            role_row = (
                await conn.execute(
                    text(
                        "SELECT current_user, rolsuper, rolbypassrls "
                        "FROM pg_roles WHERE rolname = current_user"
                    )
                )
            ).one()
            current_user, rolsuper, rolbypassrls = role_row
            # RLS enabled count on public tables (presence of policies, not table names with data)
            rls_stats = (
                await conn.execute(
                    text(
                        "SELECT "
                        "count(*) FILTER (WHERE c.relrowsecurity) AS rls_on, "
                        "count(*) FILTER (WHERE NOT c.relrowsecurity) AS rls_off, "
                        "count(*) AS total "
                        "FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relkind = 'r'"
                    )
                )
            ).one()

        print("connectivity: SUCCESS")
        print(f"select_1: {one}")
        print(f"postgres_version: {version}")
        print(f"current_user: {current_user}")
        print(f"rolsuper: {rolsuper}")
        print(f"rolbypassrls: {rolbypassrls}")
        if rolbypassrls or rolsuper:
            print("rls_mode: service-role-bypass (superuser and/or BYPASSRLS)")
        else:
            print("rls_mode: subject-to-RLS (no bypass)")
        print(
            f"public_tables_rls: on={rls_stats.rls_on} off={rls_stats.rls_off} "
            f"total={rls_stats.total}"
        )
        return 0
    except Exception as exc:
        print("connectivity: FAILURE")
        print(f"error_type: {type(exc).__name__}")
        # Avoid echoing DSN fragments that drivers sometimes embed in messages
        msg = str(exc)
        for secretish in ("password", "pwd", "user=", "@"):
            if secretish in msg.lower() and "supabase" in msg.lower():
                msg = f"{type(exc).__name__} (details redacted)"
                break
        print(f"error: {msg}")
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
