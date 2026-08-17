"""HTTP metrics middleware – O1 counter / updown / histogram on every request."""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core import telemetry as _tel


class HttpMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        if _tel.ACTIVE_REQUESTS is not None:
            _tel.ACTIVE_REQUESTS.add(1)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            labels = {
                "http.method": request.method,
                "http.route": request.url.path,
                "http.status_code": str(status),
            }
            if _tel.REQUESTS_COUNTER is not None:
                _tel.REQUESTS_COUNTER.add(1, labels)
            if _tel.REQUEST_DURATION is not None:
                _tel.REQUEST_DURATION.record(elapsed_ms, labels)
            if _tel.ACTIVE_REQUESTS is not None:
                _tel.ACTIVE_REQUESTS.add(-1)
