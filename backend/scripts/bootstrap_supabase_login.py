"""Apply login schema to hosted Supabase and seed tenant alpha.

Hosted Supabase previously only had Block D `secrets` + an incompatible
`tenants` table, so deployed login failed. This:

1. Runs alembic against SUPABASE_DB_URL (renames the old tenants table)
2. Inserts tenant `alpha` pointing at the same Supabase database
3. Seeds the documented native login users

Never prints DSNs or passwords.

Usage (from backend/):
  python scripts/bootstrap_supabase_login.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote_plus, urlparse, unquote
from uuid import uuid5, NAMESPACE_DNS

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def _supabase_url() -> str:
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        print("blocked: SUPABASE_DB_URL is not set")
        raise SystemExit(2)
    return url


def _asyncpg_control_plane_url(url: str) -> str:
    parsed = urlparse(url)
    user = quote_plus(unquote(parsed.username or "postgres"))
    password = quote_plus(unquote(parsed.password or ""))
    host = parsed.hostname or ""
    port = parsed.port or 5432
    db = (parsed.path or "/postgres").lstrip("/") or "postgres"
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def _run_alembic(async_url: str) -> None:
    env = os.environ.copy()
    env["CONTROL_PLANE_DATABASE_URL"] = async_url
    # Host process can reach Supabase; the app container often cannot (no public net).
    print("alembic: running on host against Supabase")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        check=False,
    )
    if result.returncode == 0:
        return
    print("alembic: host run failed")
    raise SystemExit(result.returncode)


def _hash_password(password: str) -> str:
    import bcrypt

    pw_bytes = password.encode("utf-8")[:71]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def _seed(url: str) -> None:
    import psycopg2

    parsed = urlparse(url)
    host = parsed.hostname or ""
    db_user = unquote(parsed.username or "postgres")
    db_password = unquote(parsed.password or "")
    db_name = (parsed.path or "/postgres").lstrip("/") or "postgres"

    tenant_id = uuid5(NAMESPACE_DNS, "snyq.supabase.tenant.alpha")
    secret_key = f"kv/tenant-{tenant_id}/db_password"
    principal_ns = uuid5(NAMESPACE_DNS, "snyq-platform.principals")

    users = [
        ("admin@synq.dev", "AlphaAdmin123!", "Alpha Admin", "admin"),
        ("member@alpha.test", "AlphaMember123!", "Alpha Member", "member"),
        ("member@synq.dev", "AlphaMember123!", "Alpha Member", "member"),
    ]

    conn = psycopg2.connect(url, sslmode="require")
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM tenants WHERE subdomain = %s", ("alpha",))
        if cur.fetchone() is None:
            cur.execute(
                """
                INSERT INTO tenants (
                    tenant_id, name, subdomain, tenancy_mode, config,
                    db_host, db_name, db_user, db_secret_key
                ) VALUES (
                    %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s
                )
                """,
                (
                    str(tenant_id),
                    "Tenant Alpha",
                    "alpha",
                    "shared_db",
                    '{"environment": "production"}',
                    host,
                    db_name,
                    db_user,
                    secret_key,
                ),
            )
            print("seed: inserted tenant alpha")
        else:
            cur.execute(
                """
                UPDATE tenants
                SET db_host = %s, db_name = %s, db_user = %s, db_secret_key = %s,
                    tenancy_mode = %s
                WHERE subdomain = %s
                """,
                (host, db_name, db_user, secret_key, "shared_db", "alpha"),
            )
            print("seed: updated tenant alpha routing")

        for email, password, display_name, role in users:
            cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
            if cur.fetchone() is not None:
                print(f"seed: user exists {email}")
                continue
            idp_subject = f"native:{email}"
            principal_id = uuid5(principal_ns, idp_subject)
            cur.execute(
                """
                INSERT INTO users (
                    principal_id, tenant_id, idp_subject, email, display_name,
                    password_hash, source_profiles, status, role,
                    must_change_password, is_active, token_version
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, '{}'::jsonb, 'active', %s,
                    false, true, 0
                )
                """,
                (
                    str(principal_id),
                    str(tenant_id),
                    idp_subject,
                    email,
                    display_name,
                    _hash_password(password),
                    role,
                ),
            )
            print(f"seed: created {role} {email}")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    _try_store_vault_secret(secret_key, db_password)
    print("seed: tenant_subdomain=alpha")
    print("seed: admin  admin@synq.dev")
    print("seed: member member@alpha.test")


def _try_store_vault_secret(key_name: str, secret_value: str) -> None:
    vault_url = (os.environ.get("VAULT_URL") or "").strip()
    tenant_id = (os.environ.get("VAULT_TENANT_ID") or "").strip()
    client_id = (os.environ.get("VAULT_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("VAULT_CLIENT_SECRET") or "").strip()
    if not (vault_url and tenant_id and client_id and client_secret):
        print("vault: skipped (Azure env not complete); set DB_PASSWORD on the host")
        return
    try:
        from azure.identity import ClientSecretCredential
        from azure.keyvault.secrets import SecretClient

        raw = (key_name or "").strip()
        chars = [ch if ch.isalnum() or ch == "-" else "-" for ch in raw]
        name = "".join(chars)
        while "--" in name:
            name = name.replace("--", "-")
        name = name.strip("-")[:127].rstrip("-")
        client = SecretClient(
            vault_url=vault_url,
            credential=ClientSecretCredential(tenant_id, client_id, client_secret),
        )
        client.set_secret(name, secret_value)
        print("vault: stored tenant db password in Azure Key Vault")
    except Exception as exc:
        print(f"vault: Azure set failed ({type(exc).__name__}); set DB_PASSWORD on the host")


def main() -> int:
    _load_dotenv()
    url = _supabase_url()
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if "supabase" not in host.lower():
        print("blocked: SUPABASE_DB_URL is not a Supabase host")
        return 2
    print(f"target: {host}:{(parsed.port or 5432)}/{(parsed.path or '/').lstrip('/')}")
    _run_alembic(_asyncpg_control_plane_url(url))
    _seed(url)
    print("bootstrap: SUCCESS")
    print("redeploy the backend so tenant SSL/password quoting is live")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
