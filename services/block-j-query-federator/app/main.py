"""FastAPI entrypoint for Block J: Query Federator and Ranking Service."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import assert_tenant_binding, get_user_context
from app.clients.embedding import EmbeddingClient
from app.config import settings
from app.models import SearchRequest, SearchResponse, UserContext
from app.services.db import close_db_engine, get_db_session, init_db_engine
from app.services.federator import Federator
from app.services.ranker import Ranker
from app.utils.logging import setup_logging
from app.utils.metrics import metrics

setup_logging()
logger = logging.getLogger(__name__)

# Process-wide singletons initialized in lifespan
_http_client: Optional[httpx.AsyncClient] = None
_ranker: Optional[Ranker] = None
_federator: Optional[Federator] = None


def get_federator() -> Federator:
    if _federator is None:
        raise RuntimeError("Federator not initialized")
    return _federator


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client, _ranker, _federator

    timeout = httpx.Timeout(
        settings.backend_timeout_seconds,
        connect=settings.backend_connect_timeout_seconds,
    )
    limits = httpx.Limits(
        max_connections=settings.http_pool_max_connections,
        max_keepalive_connections=settings.http_pool_max_keepalive,
    )
    _http_client = httpx.AsyncClient(timeout=timeout, limits=limits)
    _ranker = Ranker()
    _ranker.load()
    _federator = Federator(
        http_client=_http_client,
        ranker=_ranker,
        embedding_client=EmbeddingClient(_http_client),
    )
    init_db_engine()
    logger.info(
        "Block J Query Federator starting (lexical=%s vector=%s graph=%s reranker=%s)",
        settings.lexical_search_url,
        settings.vector_search_url,
        settings.graph_service_url,
        settings.reranker_backend,
    )
    yield
    logger.info("Block J Query Federator shutting down")
    await close_db_engine()
    if _ranker:
        _ranker.unload()
    if _http_client:
        await _http_client.aclose()
    _http_client = None
    _ranker = None
    _federator = None


app = FastAPI(
    title="Block J: Query Federator and Ranking Service",
    description=(
        "Orchestrates lexical, vector, and graph retrieval with ACL post-check "
        "and hybrid ranking for permission-safe enterprise search."
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


@app.post("/api/v1/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    user: UserContext = Depends(get_user_context),
    federator: Federator = Depends(get_federator),
    authorization: Optional[str] = Header(default=None),
    db_session: Optional[AsyncSession] = Depends(get_db_session),
) -> SearchResponse:
    """
    Federated hybrid search (internal).

    Fans out to Blocks F/G/H, applies ACL post-check, ranks, and returns
    permission-safe results with snippets, facets, and citations.
    """
    tenant_id = body.tenant_id or user.tenant_id
    assert_tenant_binding(tenant_id, user.tenant_id)
    # Ensure downstream calls use the bound tenant
    effective_user = user.model_copy(update={"tenant_id": tenant_id})

    try:
        return await federator.search(
            body,
            effective_user,
            authorization=authorization,
            db_session=db_session,
        )
    except RuntimeError as exc:
        # All backends failed
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.service_name,
        "reranker_backend": settings.reranker_backend,
        "acl_backend": settings.acl_backend,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/metrics")
async def metrics_endpoint():
    if not settings.enable_prometheus_metrics:
        raise HTTPException(status_code=404, detail="metrics disabled")
    return PlainTextResponse(metrics.prometheus_text(), media_type="text/plain")


@app.get("/")
async def root():
    return {
        "name": "Block J: Query Federator and Ranking Service",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "POST /api/v1/search": "Federated hybrid search",
            "GET /health": "Health check",
            "GET /metrics": "Prometheus metrics",
        },
    }
