"""Inspect hosted Supabase public tables. Never prints DSNs or passwords."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    raw = line.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    key, _, value = raw.partition("=")
    if key.strip() == "SUPABASE_DB_URL" and "SUPABASE_DB_URL" not in os.environ:
        os.environ["SUPABASE_DB_URL"] = value.strip()
        break

url = os.environ.get("SUPABASE_DB_URL")
if not url:
    print("connectivity: BLOCKED")
    print("reason: SUPABASE_DB_URL not set")
    raise SystemExit(2)

parsed = urlparse(url)
host = parsed.hostname or "?"
print("target_host_class:", "SUPABASE" if "supabase" in host.lower() else "OTHER")
print("target_db:", (parsed.path or "/").lstrip("/") or "?")
print("target_port:", parsed.port or 5432)

import psycopg2

conn = psycopg2.connect(url, sslmode="require")
conn.autocommit = True
cur = conn.cursor()

cur.execute(
    """
    SELECT n.nspname, c.relname, c.relrowsecurity
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
    ORDER BY 1, 2
    """
)
print("tables:")
for schema, name, rls in cur.fetchall():
    print(f"  {schema}.{name} rls={bool(rls)}")

cur.execute(
    """
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tenants'
    ORDER BY ordinal_position
    """
)
print("tenants_columns:")
rows = cur.fetchall()
if not rows:
    print("  (missing)")
else:
    for col, dtype in rows:
        print(f"  {col}: {dtype}")
    cur.execute("SELECT count(*) FROM public.tenants")
    print("tenants_rows:", cur.fetchone()[0])

cur.execute("SELECT 1 FROM pg_database WHERE datname = 'snyq_tenant_alpha'")
print("alpha_db_exists:", cur.fetchone() is not None)

try:
    cur.execute("CREATE DATABASE schema_probe_tmp")
    print("create_database: ALLOWED")
    cur.execute("DROP DATABASE schema_probe_tmp")
except Exception as exc:
    print("create_database: BLOCKED")
    print("create_database_error_type:", type(exc).__name__)

cur.execute("SELECT current_user, current_database()")
print("current_user_db:", cur.fetchone())
conn.close()
print("connectivity: SUCCESS")
