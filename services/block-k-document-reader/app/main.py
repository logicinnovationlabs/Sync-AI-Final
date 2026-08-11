"""FastAPI entrypoint for Block K: Document Reader Service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.acl.acl_checker import create_acl_checker
from app.auth.jwt_auth import get_current_user, get_tenant
from app.config import settings
from app.services.document_reader import (
    build_document_payload,
    redact_fields,
    stream_document_json,
)
from app.storage.document_store import create_document_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

store = create_document_store(settings)
acl_checker = create_acl_checker(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.connect()
    logger.info(
        "Block K Document Reader starting (storage=%s acl=%s threshold=%s)",
        settings.storage_backend,
        settings.acl_backend,
        settings.stream_threshold_bytes,
    )
    yield
    await store.close()
    logger.info("Block K Document Reader shutting down")


app = FastAPI(
    title="Block K: Document Reader Service",
    description=(
        "Full-document retrieval with ACL re-check, streaming for large bodies, "
        "and structure preservation."
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
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


@app.get("/api/v1/document/{doc_id}")
async def get_document(
    doc_id: str,
    tenant_id: str = Depends(get_tenant),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """GET full document by ID with ACL re-check and optional streaming."""
    principal_id = str(
        current_user.get("principal_id")
        or current_user.get("sub")
        or current_user.get("user_id")
        or ""
    )
    if not principal_id:
        raise HTTPException(status_code=401, detail="principal_id missing from token")

    metadata = await store.get_metadata(tenant_id, doc_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Document not found")

    # K1: ACL re-check on every request — no caching
    allowed = await acl_checker.is_allowed(tenant_id, principal_id, doc_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="Forbidden")

    object_key = metadata.get("object_key")
    if not object_key:
        raise HTTPException(status_code=500, detail="Document object missing")

    visible_metadata = redact_fields(metadata, principal_id)
    structured_data = await store.get_structured_metadata(tenant_id, doc_id)
    body_size = int(metadata.get("body_size") or 0)

    if body_size > settings.stream_threshold_bytes:
        # K2: stream large documents with bounded memory
        return StreamingResponse(
            stream_document_json(
                store,
                object_key,
                doc_id,
                tenant_id,
                visible_metadata,
                structured_data,
            ),
            media_type="application/json",
            headers={"X-Document-Streaming": "1", "X-Document-Size": str(body_size)},
        )

    try:
        raw = await store.get_body(object_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document body not found") from exc

    body = raw.decode("utf-8", errors="replace")
    return build_document_payload(
        doc_id=doc_id,
        tenant_id=tenant_id,
        visible_metadata=visible_metadata,
        body=body,
        structured_data=structured_data,
    )


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.service_name,
        "storage_backend": settings.storage_backend,
        "acl_backend": settings.acl_backend,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    return {
        "name": "Block K: Document Reader Service",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "GET /api/v1/document/{id}": "Full document retrieval with ACL re-check",
            "GET /health": "Health check",
        },
    }
