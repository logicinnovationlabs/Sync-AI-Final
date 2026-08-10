"""FastAPI entrypoint for Block H: Knowledge Graph Service."""

from contextlib import asynccontextmanager
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.admin import router as admin_router
from app.api.v1.people import router as people_router
from app.api.v1.related import router as related_router
from app.api.v1.traverse import router as traverse_router
from app.config import settings
from app.services.factory import get_graph_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Block H Knowledge Graph starting (backend=%s, neo4j=%s)",
        settings.graph_backend,
        settings.neo4j_uri,
    )
    yield
    logger.info("Block H Knowledge Graph shutting down")


app = FastAPI(
    title="Block H: Knowledge Graph Service",
    description=(
        "Tenant-isolated graph traversal, people search, and related-entity "
        "lookup for the Query Federator (Block J)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment != "production" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "BAD_REQUEST",
                "message": "Malformed request",
                "details": exc.errors(),
            },
            "request_id": request.headers.get("X-Request-ID"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
            },
            "request_id": request.headers.get("X-Request-ID"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# Master-prompt paths at root AND /api/v1 for Block J consistency
for r in (traverse_router, people_router, related_router, admin_router):
    app.include_router(r)
    app.include_router(r, prefix="/api/v1")


@app.get("/health")
async def health_check():
    store = get_graph_store()
    ok, detail = await store.health()
    status_code_hint = "healthy" if ok else "degraded"
    return {
        "status": status_code_hint,
        "service": "block-h-graph",
        "graph_backend": settings.graph_backend,
        "backend_detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    return {
        "name": "Block H: Knowledge Graph Service",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "POST /graph/traverse": "Depth-limited relationship expansion",
            "GET /people/search": "People / principal search",
            "GET /graph/related/{id}": "Related-entity lookup",
            "POST /admin/persons/merge": "Merge two Person nodes (admin)",
            "POST /admin/persons/split": "Split/restore a Person merge (admin)",
            "GET /health": "Health check",
        },
    }
