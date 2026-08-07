"""FastAPI entrypoint for Block F: Lexical Search Service."""

from contextlib import asynccontextmanager
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.index import router as index_router
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
        "Block F Lexical Search starting (backend=%s, opensearch=%s:%s)",
        settings.search_backend,
        settings.opensearch_host,
        settings.opensearch_port,
    )
    yield
    logger.info("Block F Lexical Search shutting down")


app = FastAPI(
    title="Block F: Lexical Search Service",
    description=(
        "Keyword retrieval with mandatory ACL enforcement, faceting, and snippets "
        "for the Query Federator (Block J)."
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


# Master prompt contract: POST /search/lexical and POST /_internal/index
# Also mounted under /api/v1 for consistency with Block G
app.include_router(search_router)
app.include_router(index_router)
app.include_router(search_router, prefix="/api/v1")
app.include_router(index_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "block-f-lexical-search",
        "search_backend": settings.search_backend,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    return {
        "name": "Block F: Lexical Search Service",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "POST /search/lexical": "ACL-prefiltered BM25 lexical search",
            "POST /_internal/index": "Index writer for canonical documents",
            "GET /health": "Health check",
        },
    }
