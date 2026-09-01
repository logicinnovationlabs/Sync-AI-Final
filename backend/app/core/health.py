"""Liveness and readiness probes for orchestrators."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.storage.control_plane_db import ControlPlaneSessionLocal
from app.storage.redis_client import redis_client

logger = logging.getLogger(__name__)


async def liveness_payload() -> Dict[str, Any]:
    """Process is up — no dependency checks."""
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.environment,
    }


async def _check_postgres() -> tuple[bool, str]:
    try:
        async with ControlPlaneSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


async def _check_redis() -> tuple[bool, str]:
    try:
        if redis_client._client is None:
            await redis_client.connect()
        if redis_client._client is None:
            return False, "redis unavailable (fallback mode)"
        await redis_client._client.ping()
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


async def _check_http(name: str, url: str | None) -> tuple[bool, str]:
    if not url:
        return True, "not configured"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url)
            if resp.status_code < 500:
                return True, f"http {resp.status_code}"
            return False, f"http {resp.status_code}"
    except Exception as exc:
        return False, str(exc)


async def readiness_payload() -> Dict[str, Any]:
    """Deep checks for load balancers / k8s readiness."""
    checks: Dict[str, Dict[str, Any]] = {}

    ok, detail = await _check_postgres()
    checks["postgres"] = {"ok": ok, "detail": detail}

    ok, detail = await _check_redis()
    checks["redis"] = {"ok": ok, "detail": detail}

    opensearch_url = settings.resolved_lexical_url
    if settings.lexical_enabled:
        ok, detail = await _check_http("opensearch", opensearch_url)
    else:
        ok, detail = True, "not configured"
    checks["opensearch"] = {"ok": ok, "detail": detail}

    qdrant_url = settings.qdrant_url
    if not qdrant_url and settings.qdrant_host:
        qdrant_url = f"http://{settings.qdrant_host}:{settings.qdrant_port}"
    ok, detail = await _check_http("qdrant", qdrant_url)
    checks["qdrant"] = {"ok": ok, "detail": detail}

    vault_ok = True
    vault_detail = "mock" if not settings.vault_url else "configured"
    if settings.vault_url:
        vault_ok = True
        vault_detail = settings.vault_url
    checks["vault"] = {"ok": vault_ok, "detail": vault_detail}

    required = ["postgres", "redis"]
    if settings.environment not in ("development", "dev", "test"):
        if settings.lexical_enabled:
            required.append("opensearch")
        if settings.qdrant_url or settings.qdrant_host:
            required.append("qdrant")

    failed: List[str] = [
        name for name in required if not checks.get(name, {}).get("ok")
    ]
    status = "ready" if not failed else "not_ready"
    return {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failed": failed,
    }
