"""FastAPI entrypoint for Block G: Vector Search Service."""

from contextlib import asynccontextmanager
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.ingest import router as ingest_router
from app.api.v1.search import router as search_router
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Block G Vector Search starting (db=%s, host=%s:%s)",
        settings.vector_db_type,
        settings.qdrant_host,
        settings.qdrant_port,
    )
    yield
    logger.info("Block G Vector Search shutting down")


app = FastAPI(
    title="Block G: Vector Search Service",
    description=(
        "Tenant-isolated, ACL-prefiltered ANN retrieval for the Query Federator (Block J)."
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


# Master prompt contract: /api/v1/search/vector and /api/v1/ingest
app.include_router(search_router, prefix="/api/v1")
app.include_router(ingest_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "block-g-vector-search",
        "vector_db_type": settings.vector_db_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    return {
        "name": "Block G: Vector Search Service",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "POST /api/v1/search/vector": "ACL-prefiltered ANN search",
            "POST /api/v1/ingest": "Upsert chunk embeddings from Block E",
            "GET /health": "Health check",
        },
    }