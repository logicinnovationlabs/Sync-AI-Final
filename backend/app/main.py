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
from app.connectors.google.webhooks import router as webhooks_router
from app.connectors.router import router as connectors_router
from app.connectors.org import router as connectors_org_router

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

_cors_origins = settings.cors_origins_list
if _is_relaxed_env and not _cors_origins:
    _cors_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# Mount routers under /api/v1 only (single canonical prefix)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(oauth.router, prefix="/api/v1")
app.include_router(me.router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1", tags=["admin"])
app.include_router(tenant_bootstrap_router, prefix="/admin", tags=["admin"])
app.include_router(connectors_router, prefix="/api/v1")
app.include_router(connectors_org_router, prefix="/api/v1")
app.include_router(scoped_probes.router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(identity_routes.router, prefix="/api/v1")
app.include_router(acl_routes.router, prefix="/api/v1")
app.include_router(embed.router, prefix="/api/v1", tags=["embeddings"])
app.include_router(lexical.router, prefix="/api/v1", tags=["search-lexical"])
app.include_router(vector.router, prefix="/api/v1", tags=["search-vector"])
app.include_router(graph_search.router, prefix="/api/v1", tags=["search-graph"])
app.include_router(signals_routes.router, prefix="/api/v1", tags=["signals"])
app.include_router(federated_search.router, prefix="/api/v1", tags=["search-federated"])
app.include_router(document_routes.router, prefix="/api/v1", tags=["document-reader"])
app.include_router(assistant_routes.router, prefix="/api/v1/assistant", tags=["assistant"])
app.include_router(mcp_gateway_router, prefix="/api/v1")


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
