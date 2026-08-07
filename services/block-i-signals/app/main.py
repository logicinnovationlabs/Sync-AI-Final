"""FastAPI entrypoint for Block I: Activity Ingestion and Signal Service."""

from contextlib import asynccontextmanager
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.ingest import router as ingest_router
from app.api.v1.signals import router as signals_router
from app.config import settings
from app.consumers.activity_consumer import start_activity_consumer, stop_activity_consumer
from app.jobs.retention import start_retention_job, stop_retention_job
from app.services.factory import get_activity_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Block I Activity/Signals starting (backend=%s, privacy_threshold=%s)",
        settings.signals_backend,
        settings.privacy_threshold,
    )
    start_retention_job()
    start_activity_consumer()
    yield
    await stop_activity_consumer()
    await stop_retention_job()
    logger.info("Block I Activity/Signals shutting down")


app = FastAPI(
    title="Block I: Activity Ingestion and Signal Service",
    description=(
        "Ingests user activity events, enforces privacy thresholds and retention, "
        "and serves per-user / aggregate document signals for ranking and personalisation."
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


# Master-prompt paths at root AND /api/v1 for gateway consistency
for r in (ingest_router, signals_router):
    app.include_router(r)
    app.include_router(r, prefix="/api/v1")


@app.get("/health")
async def health_check():
    store = get_activity_store()
    ok, detail = await store.health()
    return {
        "status": "healthy" if ok else "degraded",
        "service": "block-i-signals",
        "signals_backend": settings.signals_backend,
        "backend_detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    return {
        "name": "Block I: Activity Ingestion and Signal Service",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "POST /activity/ingest": "Ingest activity events (scope: activity.ingest)",
            "GET /signals/user/{user_id}": "Per-user signal vector (scope: signals.read)",
            "GET /signals/document/{document_id}": "Privacy-gated document popularity",
            "POST /admin/retention/purge": "Trigger TTL purge",
            "GET /health": "Health check",
        },
    }
