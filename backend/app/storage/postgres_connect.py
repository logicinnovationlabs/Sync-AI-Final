"""Postgres DSN helpers: SSL for hosted hosts, never for local Docker."""

from __future__ import annotations

import ssl
from typing import Optional
from urllib.parse import quote_plus, urlparse


def hostname_from_url(url: str) -> Optional[str]:
    normalized = (
        url.replace("postgresql+asyncpg://", "postgresql://", 1)
        .replace("postgres://", "postgresql://", 1)
    )
    return urlparse(normalized).hostname


def is_local_postgres_host(host: Optional[str]) -> bool:
    hostname = (host or "").split("/")[0].split(":")[0].lower()
    return hostname in {"localhost", "127.0.0.1", "postgres", "::1"} or hostname.endswith(
        ".local"
    )


def _hosted_ssl_context() -> ssl.SSLContext:
    """TLS for Supabase / cloud Postgres.

    `ssl=True` uses the default cert store and fails on Windows with
    Supabase's chain (`CERTIFICATE_VERIFY_FAILED`). Encrypt the session
    the same way `sslmode=require` does.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def connect_args_for_host(host: Optional[str]) -> dict:
    """asyncpg: local Docker needs ssl=False; cloud hosts need TLS."""
    if is_local_postgres_host(host):
        return {"ssl": False}
    return {"ssl": _hosted_ssl_context()}


def connect_args_for_url(url: str) -> dict:
    return connect_args_for_host(hostname_from_url(url))


def asyncpg_database_url(user: str, password: str, host: str, db_name: str) -> str:
    if ":" not in host:
        host = f"{host}:5432"
    return (
        f"postgresql+asyncpg://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}/{db_name}"
    )
