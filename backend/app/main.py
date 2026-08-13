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

from app.core.config import settings
from app.core.exceptions import SnyQException
from app.core.errors import ErrorResponse, ErrorDetail
from app.api.v1 import auth, oauth, me, admin, connectors, scoped_probes, embed, signals as signals_routes
from app.api.v1 import identity as identity_routes
from app.api.v1 import acl as acl_routes
from app.api.v1.search import lexical, vector
from app.api.v1.search import graph as graph_search
from app.api.v1.search import federated as federated_search
from app.connectors.google.webhooks import router as webhooks_router

from app.middleware.tenant_middleware import TenantMiddleware
from app.storage.redis_client import redis_client
from app.storage.control_plane_db import control_plane_engine
from app.storage.tenant_db import tenant_db_manager


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events.
    """
    # Startup
    logger.info("SnyQ Backend starting up...")
    await redis_client.connect()
    logger.info("Connected to Redis")
    
    yield
    
    # Shutdown
    logger.info("SnyQ Backend shutting down...")
    await redis_client.disconnect()
    await tenant_db_manager.close_all()
    await control_plane_engine.dispose()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="SnyQ Backend API",
    description="Block A: Tenancy, Identity, and Auth Platform",
    version="0.1.0",
    lifespan=lifespan,
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Tenant resolution middleware
app.add_middleware(TenantMiddleware)


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


# Mount routers (both with /api/v1 prefix and root level for client compatibility)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(oauth.router, prefix="/api/v1")
app.include_router(oauth.router)
app.include_router(me.router, prefix="/api/v1")
app.include_router(me.router)
app.include_router(admin.router, prefix="/api/v1")
app.include_router(admin.router)
app.include_router(connectors.router, prefix="/api/v1")
app.include_router(connectors.router)
app.include_router(scoped_probes.router, prefix="/api/v1")
app.include_router(scoped_probes.router)
app.include_router(webhooks_router, prefix="/api/v1")
# Block C: identity resolution + ACL debug endpoints
app.include_router(identity_routes.router, prefix="/api/v1")
app.include_router(identity_routes.router)
app.include_router(acl_routes.router, prefix="/api/v1")
app.include_router(acl_routes.router)
# Block E: Chunking & Embeddings
app.include_router(embed.router, prefix="/api/v1", tags=["embeddings"])
app.include_router(embed.router, tags=["embeddings"])
# Block F: Lexical Search
app.include_router(lexical.router, prefix="/api/v1", tags=["search-lexical"])
app.include_router(lexical.router, tags=["search-lexical"])
# Block G: Vector Search
app.include_router(vector.router, prefix="/api/v1", tags=["search-vector"])
app.include_router(vector.router, tags=["search-vector"])
# Block H: Graph Search
app.include_router(graph_search.router, prefix="/api/v1", tags=["search-graph"])
app.include_router(graph_search.router, tags=["search-graph"])
# Block I: Activity Signals
app.include_router(signals_routes.router, prefix="/api/v1", tags=["signals"])
app.include_router(signals_routes.router, tags=["signals"])
# Block J: Federated Search
app.include_router(federated_search.router, prefix="/api/v1", tags=["search-federated"])
app.include_router(federated_search.router, tags=["search-federated"])



# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "environment": settings.environment,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "SnyQ Backend API",
        "version": "0.1.0",
        "block": "A: Tenancy, Identity, and Auth Platform",
        "docs": "/docs",
    }
