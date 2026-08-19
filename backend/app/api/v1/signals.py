"""Block I: Activity Ingestion and Signal APIs."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_scope
from app.core.config import settings
from app.models.activity import (
    DocumentSignalResponse,
    FailedEvent,
    IngestRequest,
    IngestResponse,
    UserSignalResponse,
)
from app.services.signals import ActivityStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["signals"])

# Simple metrics tracking
_METRICS = {
    "ingest_count": 0,
    "ingest_latency": [],
    "signal_latency": [],
}


def get_activity_store() -> ActivityStore:
    """Process-level activity store (singleton mock in development/test)."""
    from app.services.signals import get_activity_store as _factory

    try:
        return _factory()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ==================== Ingestion ====================


@router.post("/activity/ingest", response_model=IngestResponse)
async def ingest_activity(
    body: IngestRequest,
    current_user: Dict[str, Any] = Depends(require_scope("activity.ingest")),
    store: ActivityStore = Depends(get_activity_store),
) -> IngestResponse:
    """
    Ingest one or more activity events.

    tenant_id is taken exclusively from the JWT, never from the body.
    Duplicate event_id within a tenant is a no-op (already_processed).
    """
    tenant_id = str(current_user.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing from token")

    ingested = 0
    already = 0
    failed: list[FailedEvent] = []
    started = time.perf_counter()

    for event in body.events:
        if event.tenant_id and event.tenant_id != tenant_id:
            failed.append(
                FailedEvent(
                    event_id=event.event_id,
                    reason="tenant_id in body does not match token",
                )
            )
            continue
        try:
            result = await store.ingest_event(tenant_id, event)
            if result == "ingested":
                ingested += 1
            else:
                already += 1
        except ValueError as exc:
            failed.append(FailedEvent(event_id=event.event_id, reason=str(exc)))
        except Exception as exc:
            logger.exception("ingest failed for %s: %s", event.event_id, exc)
            failed.append(FailedEvent(event_id=event.event_id, reason="internal_error"))

    _METRICS["ingest_count"] += ingested
    _METRICS["ingest_latency"].append(time.perf_counter() - started)
    if len(_METRICS["ingest_latency"]) > 1000:
        _METRICS["ingest_latency"] = _METRICS["ingest_latency"][-500:]

    status = "accepted" if not failed else ("partial" if ingested or already else "rejected")
    return IngestResponse(
        status=status,
        ingested_count=ingested,
        already_processed_count=already,
        failed_events=failed,
    )


# ==================== Signals ====================


@router.get("/signals/user/{user_id}", response_model=UserSignalResponse)
async def get_user_signals(
    user_id: str,
    current_user: Dict[str, Any] = Depends(require_scope("signals.read")),
    store: ActivityStore = Depends(get_activity_store),
) -> UserSignalResponse:
    """
    Per-user affinity feature vector.

    Caller must be bound to the same tenant.
    """
    tenant_id = str(current_user.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing from token")

    started = time.perf_counter()
    try:
        resp = await store.get_user_signals(tenant_id, user_id)
        return resp
    finally:
        _METRICS["signal_latency"].append(time.perf_counter() - started)
        if len(_METRICS["signal_latency"]) > 1000:
            _METRICS["signal_latency"] = _METRICS["signal_latency"][-500:]


@router.get("/signals/document/{document_id}", response_model=DocumentSignalResponse)
async def get_document_signals(
    document_id: str,
    current_user: Dict[str, Any] = Depends(require_scope("signals.read")),
    store: ActivityStore = Depends(get_activity_store),
) -> DocumentSignalResponse:
    """
    Aggregate document popularity, privacy-threshold protected.

    When distinct actors < tenant privacy_threshold, returns privacy_protected=true
    and null numeric fields.
    """
    tenant_id = str(current_user.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing from token")

    started = time.perf_counter()
    try:
        return await store.get_document_signals(tenant_id, document_id)
    finally:
        _METRICS["signal_latency"].append(time.perf_counter() - started)
        if len(_METRICS["signal_latency"]) > 1000:
            _METRICS["signal_latency"] = _METRICS["signal_latency"][-500:]


@router.post("/admin/retention/purge")
async def purge_retention(
    current_user: Dict[str, Any] = Depends(require_scope("signals.admin")),
    store: ActivityStore = Depends(get_activity_store),
) -> Dict[str, Any]:
    """Manually trigger retention purge (also run by scheduled job)."""
    result = await store.purge_expired()
    return result.model_dump()


@router.get("/signals/metrics")
async def metrics(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Internal metrics for observability."""
    ingest_lat = _METRICS["ingest_latency"]
    signal_lat = _METRICS["signal_latency"]
    
    ingest_p95 = None
    if ingest_lat:
        ordered = sorted(ingest_lat)
        idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
        ingest_p95 = ordered[idx]
    
    signal_p95 = None
    if signal_lat:
        ordered = sorted(signal_lat)
        idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
        signal_p95 = ordered[idx]
    
    return {
        "ingest_count": _METRICS["ingest_count"],
        "ingest_p95_seconds": ingest_p95,
        "signal_p95_seconds": signal_p95,
    }
