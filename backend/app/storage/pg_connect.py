"""Normalize Postgres URLs for asyncpg on local Docker and IPv4-only hosts (Render).

Render cannot open outbound IPv6. Supabase *direct* hosts (``db.<ref>.supabase.co``)
are IPv6-only and fail with ``OSError: [Errno 101] Network is unreachable``.
Use the Session pooler host instead, or set ``SUPABASE_POOLER_URL``.
"""

from __future__ import annotations

import os
import re
import ssl
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None  # type: ignore[assignment]

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres"}
_DIRECT_SUPABASE = re.compile(r"^db\.([a-z0-9]+)\.supabase\.co$", re.I)


def is_local_pg_host(host: Optional[str]) -> bool:
    h = (host or "").split("%")[0].lower()
    return h in _LOCAL_HOSTS or h.endswith(".local")


def to_asyncpg_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+asyncpg" not in url[: len("postgresql+asyncpg")]:
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def _as_libpq(url: str) -> str:
    return to_asyncpg_url(url).replace("postgresql+asyncpg://", "postgresql://", 1)


def _netloc(user: str, password: str, host: str, port: int) -> str:
    auth = quote(user, safe="")
    if password:
        auth = f"{auth}:{quote(password, safe='')}"
    host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"{auth}@{host_part}:{port}"


def _host_of(url: str) -> str:
    if not url:
        return ""
    return urlparse(_as_libpq(url)).hostname or ""


def is_supabase_pooler_host(host: Optional[str]) -> bool:
    return "pooler.supabase.com" in (host or "").lower()


def is_supabase_direct_host(host: Optional[str]) -> bool:
    return bool(_DIRECT_SUPABASE.match(host or ""))


def prepare_database_url(
    url: str,
    *,
    fallback_cloud_url: str = "",
    pooler_url: str = "",
    pooler_host: str = "",
) -> str:
    """Return an asyncpg URL that can actually connect from this host."""
    url = to_asyncpg_url(url)
    if not url:
        return url

    pooler_url = (pooler_url or os.getenv("SUPABASE_POOLER_URL") or "").strip()
    pooler_host = (pooler_host or os.getenv("SUPABASE_POOLER_HOST") or "").strip()
    fallback_cloud_url = (
        fallback_cloud_url or os.getenv("SUPABASE_DB_URL") or ""
    ).strip()
    on_render = os.getenv("RENDER", "").lower() in ("true", "1", "yes")

    parsed = urlparse(_as_libpq(url))
    host = parsed.hostname or ""
    port = parsed.port or 5432
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.pop("sslmode", None)
    query.pop("ssl", None)

    def _prefer(cloud: str) -> str:
        return prepare_database_url(
            cloud,
            fallback_cloud_url="",
            pooler_url="",
            pooler_host=pooler_host,
        )

    if on_render and is_local_pg_host(host):
        cloud = pooler_url or fallback_cloud_url
        if cloud and cloud != url:
            return _prefer(cloud)

    # Direct db.<ref>.supabase.co is IPv6-only. Prefer any pooler URI we have.
    pooler_candidate = ""
    for candidate in (pooler_url, fallback_cloud_url):
        if candidate and is_supabase_pooler_host(_host_of(candidate)):
            pooler_candidate = candidate
            break
    direct = _DIRECT_SUPABASE.match(host)
    if direct and pooler_candidate:
        return _prefer(pooler_candidate)
    if direct and pooler_url:
        return _prefer(pooler_url)
    if direct and pooler_host:
        ref = direct.group(1)
        if user in ("postgres", "authenticator"):
            user = f"postgres.{ref}"
        host = pooler_host
        if port == 5432 and "pooler.supabase.com" in pooler_host:
            port = 5432

    if host in ("localhost", "::1"):
        host = "127.0.0.1"

    rebuilt = parsed._replace(
        netloc=_netloc(user, password, host, port),
        query=urlencode(query),
    )
    return "postgresql+asyncpg://" + urlunparse(rebuilt).removeprefix("postgresql://")


def _cloud_ssl_context(*, host: str = "") -> ssl.SSLContext:
    """TLS for Supabase / managed Postgres on slim hosts (Render Docker).

    The Supabase session pooler chain fails strict verify on Render's slim image
    (``CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain``).
    Connection is still encrypted; we skip CA verify only for the pooler host.
    """
    if is_supabase_pooler_host(host):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def connect_args_for_url(url: str) -> Dict[str, Any]:
    """asyncpg connect_args. Local Docker must disable TLS; cloud Postgres requires it."""
    parsed = urlparse(_as_libpq(url))
    host = parsed.hostname or ""
    port = parsed.port or 5432
    if is_local_pg_host(host):
        return {"ssl": False}
    args: Dict[str, Any] = {"ssl": _cloud_ssl_context(host=host), "timeout": 10}
    # Transaction-mode pooler (PgBouncer / Supavisor :6543) cannot cache statements.
    if port == 6543 or is_supabase_pooler_host(host):
        args["statement_cache_size"] = 0
    return args
