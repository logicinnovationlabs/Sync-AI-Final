"""Simple Redis-backed rate limiting for anonymous and authenticated traffic."""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.storage.redis_client import redis_client

logger = logging.getLogger(__name__)

_EXEMPT_PREFIXES = (
    "/health",
    "/ready",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiter keyed by client IP (and tenant when present)."""

    def __init__(self, app, requests_per_minute: Optional[int] = None):
        super().__init__(app)
        self.limit = int(
            requests_per_minute
            if requests_per_minute is not None
            else getattr(settings, "rate_limit_per_minute", 120)
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if (
            self.limit <= 0
            or request.method == "OPTIONS"
            or request.url.path.startswith(_EXEMPT_PREFIXES)
        ):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        tenant_hint = request.headers.get("X-Tenant-ID", "")
        bucket = f"ratelimit:{client_ip}:{tenant_hint}"
        window = int(time.time() // 60)

        try:
            if redis_client._client is None:
                await redis_client.connect()
            if redis_client._client is not None:
                key = f"global:{bucket}:{window}"
                count = await redis_client._client.incr(key)
                if count == 1:
                    await redis_client._client.expire(key, 60)
                if count > self.limit:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": "Too many requests",
                            }
                        },
                    )
        except Exception as exc:
            logger.debug("Rate limit skipped: %s", exc)

        return await call_next(request)
