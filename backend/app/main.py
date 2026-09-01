"""
FastAPI application entrypoint.

Mounts all routers, configures middleware, handles startup/shutdown.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime

import app.core.compat  # noqa: F401 — pkg_resources shim for Python 3.12+

from app.core.config import settings
from app.core.telemetry import setup_telemetry, instrument_fastapi
from app.core.logging import setup_otel_logging
from app.core.startup import validate_startup_config, StartupConfigurationError
from app.core.health import liveness_payload, readiness_payload

# Block O – OpenTelemetry bootstrap (MUST run before FastAPI app is created)
setup_telemetry(service_name="snyq-backend")
from app.core.exceptions import SnyQException
from app.core.errors import ErrorResponse, ErrorDetail
from app.api.v1 import auth, oauth, me, scoped_probes, embed, signals as signals_routes
from app.api.v1.admin import admin_router
from app.api.v1.admin.tenant import router as tenant_bootstrap_router
from app.api.v1 import identity as identity_routes
from app.api.v1 import acl as acl_routes
from app.api.v1.search import lexical, vector
from app.api.v1.search import graph as graph_search
from app.api.v1.search import federated as federated_search
from app.services.assistant.api import routes as assistant_routes
from app.api.v1 import document as document_routes
from app.services.mcp_gateway import router as mcp_gateway_router
from app.connectors.router import router as connectors_router
from app.connectors.org import router as connectors_org_router
from app.connectors import provider_registry
from app.api.v1 import reindex as reindex_routes
from app.api.v1 import acl_debug as acl_debug_routes

from app.middleware.tenant_middleware import TenantMiddleware
from app.middleware.http_metrics import HttpMetricsMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.storage.redis_client import redis_client
from app.storage.control_plane_db import control_plane_engine
from app.storage.tenant_db import tenant_db_manager
from app.services.mcp_gateway.revocation import mcp_revocation_listener


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - [trace=%(trace_id)s span=%(span_id)s] %(message)s",
)
setup_otel_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events.
    """
    # Startup
    logger.info("SnyQ Backend starting up...")
    try:
        validate_startup_config()
    except StartupConfigurationError as exc:
        logger.critical("Startup configuration invalid: %s", exc)
        raise
    await redis_client.connect()
    if redis_client._client is None:
        logger.warning("Redis unavailable — running in in-memory fallback")
    else:
        logger.info("Connected to Redis")
    await mcp_revocation_listener.start()

    yield

    # Shutdown
    logger.info("SnyQ Backend shutting down...")
    await mcp_revocation_listener.stop()
    await redis_client.disconnect()
    await tenant_db_manager.close_all()
    await control_plane_engine.dispose()
    logger.info("Shutdown complete")


# Create FastAPI app — hide OpenAPI in production/staging
_is_relaxed_env = settings.environment.lower() in ("development", "dev", "test")
app = FastAPI(
    title="SnyQ Backend API",
    description="Block A: Tenancy, Identity, and Auth Platform",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _is_relaxed_env else None,
    redoc_url="/redoc" if _is_relaxed_env else None,
    openapi_url="/openapi.json" if _is_relaxed_env else None,
)

# Block O – Middleware ordering matters. In Starlette, add_middleware() wraps
# earlier middleware. Execution order is reverse of add order:
#   TenantMiddleware (innermost, runs closest to route — span is active here)
#   FastAPIInstrumentor (creates the span)
#   CORSMiddleware (outermost)
# TenantMiddleware MUST be added before FastAPIInstrumentor so it runs AFTER
# the span is created, allowing tenant.id to be set on a recording span.
app.add_middleware(TenantMiddleware)
app.add_middleware(HttpMetricsMiddleware)
app.add_middleware(RateLimitMiddleware)

# Browsers reject allow_origins=["*"] together with allow_credentials=True.
# Always allow *.vercel.app via regex so prod + preview deployments work even when
# CORS_ALLOWED_ORIGINS lists only one Vercel URL (setting origins disables regex
# unless we set both — this was breaking UI login while Postman still worked).
_cors_origins = settings.effective_cors_origins
_cors_regex = r"https://([a-z0-9-]+\.)*vercel\.app"
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Block O – instrument FastAPI (needs the app object)
instrument_fastapi(app)


# Exception handlers
@app.exception_handler(SnyQException)
async def snyq_exception_handler(request: Request, exc: SnyQException):
    """Handle custom SnyQ exceptions with error envelope."""
    error_response = ErrorResponse(
        error=ErrorDetail(
            code=exc.__class__.__name__,
            message=exc.message,
        ),
        request_id=request.headers.get("X-Request-ID"),
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.dict(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.exception("Unhandled exception")
    error_response = ErrorResponse(
        error=ErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred",
        ),
        request_id=request.headers.get("X-Request-ID"),
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
    return JSONResponse(
        status_code=500,
        content=error_response.dict(),
    )


def _include_product_and_legacy(router, **kwargs) -> None:
    """Mount at the frontend/OAuth path and again under /api/v1.

    The UI, Google redirect URI, and connector tests call `/auth/login`,
    `/connectors/...`, `/me`, etc. Older clients and contracts.yaml still
    use `/api/v1/...`. Both must resolve or post-login Celery enqueue 404s.
    """
    extra_prefix = kwargs.pop("prefix", "")
    app.include_router(router, prefix=extra_prefix, **kwargs)
    app.include_router(router, prefix=f"/api/v1{extra_prefix}", **kwargs)


_include_product_and_legacy(auth.router)
_include_product_and_legacy(oauth.router)
_include_product_and_legacy(me.router)
_include_product_and_legacy(admin_router, tags=["admin"])
app.include_router(tenant_bootstrap_router, prefix="/admin", tags=["admin"])
_include_product_and_legacy(connectors_router)
_include_product_and_legacy(connectors_org_router)
# Legacy + webhook routes declared by provider plugins (e.g. /outlook/callback)
for _plugin in provider_registry.all_plugins():
    for path, endpoint, methods in _plugin.legacy_routes or ():
        app.add_api_route(
            path, endpoint, methods=list(methods), include_in_schema=False
        )
_include_product_and_legacy(scoped_probes.router)
for _plugin in provider_registry.all_plugins():
    if _plugin.webhook_router is not None:
        _include_product_and_legacy(_plugin.webhook_router)
_include_product_and_legacy(identity_routes.router)
_include_product_and_legacy(acl_routes.router)
_include_product_and_legacy(embed.router, tags=["embeddings"])
_include_product_and_legacy(lexical.router, tags=["search-lexical"])
_include_product_and_legacy(vector.router, tags=["search-vector"])
_include_product_and_legacy(graph_search.router, tags=["search-graph"])
_include_product_and_legacy(signals_routes.router, tags=["signals"])
_include_product_and_legacy(federated_search.router, tags=["search-federated"])
_include_product_and_legacy(document_routes.router, tags=["document-reader"])
_include_product_and_legacy(assistant_routes.router, prefix="/assistant", tags=["assistant"])
_include_product_and_legacy(mcp_gateway_router)
_include_product_and_legacy(reindex_routes.router, tags=["reindex"])
# Only include debug routes in development/test environments for security
if _is_relaxed_env:
    _include_product_and_legacy(acl_debug_routes.router, tags=["acl-debug"])


# Probes
@app.get("/health")
async def health_check():
    """Liveness probe — process is running."""
    return await liveness_payload()


@app.get("/ready")
async def readiness_check():
    """Readiness probe — critical dependencies must be reachable."""
    payload = await readiness_payload()
    status_code = 200 if payload["status"] == "ready" else 503
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/")
async def root():
    """Root endpoint."""
    docs = "/docs" if _is_relaxed_env else None
    return {
        "name": "SnyQ Backend API",
        "version": "0.1.0",
        "block": "A: Tenancy, Identity, and Auth Platform",
        "docs": docs,
    }
