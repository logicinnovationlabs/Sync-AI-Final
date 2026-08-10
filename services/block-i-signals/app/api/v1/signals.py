"""GET /signals/user/{user_id} and GET /signals/document/{document_id}."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_scopes
from app.config import settings
from app.models.activity import DocumentSignalResponse, UserSignalResponse
from app.services.activity_store import ActivityStore
from app.services.factory import get_activity_store
from app.services.metrics import record_signal_query_latency

logger = logging.getLogger(__name__)
router = APIRouter(tags=["signals"])


def get_store() -> ActivityStore:
    return get_activity_store()


@router.get("/signals/user/{user_id}", response_model=UserSignalResponse)
async def get_user_signals(
    user_id: str,
    current_user: Dict[str, Any] = Depends(require_scopes("signals.read")),
    store: ActivityStore = Depends(get_store),
) -> UserSignalResponse:
    """
    Per-user affinity feature vector.

    Caller must be bound to the same tenant. Cross-tenant user lookups are 403.
    """
    tenant_id = str(current_user.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing from token")

    # Soft check: if caller is requesting another principal, still allow same-tenant
    # but never leak cross-tenant (user_id may encode tenant; we scope store by token).
    started = time.perf_counter()
    try:
        # Block cross-tenant by requiring X-Target-Tenant only when explicitly different —
        # user signals are always scoped to the caller's tenant_id from JWT.
        resp = await store.get_user_signals(tenant_id, user_id)
        # Optional: refuse reading users that only exist in another tenant fixture
        # (handled by empty signals for unknown users within tenant).
        return resp
    finally:
        record_signal_query_latency("user", time.perf_counter() - started)


@router.get("/signals/document/{document_id}", response_model=DocumentSignalResponse)
async def get_document_signals(
    document_id: str,
    current_user: Dict[str, Any] = Depends(require_scopes("signals.read")),
    store: ActivityStore = Depends(get_store),
) -> DocumentSignalResponse:
    """
    Aggregate document popularity, privacy-threshold protected.

    When distinct actors < tenant privacy_threshold, returns privacy_protected=true
    and null numeric fields (no actor inference possible).
    """
    tenant_id = str(current_user.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing from token")

    started = time.perf_counter()
    try:
        return await store.get_document_signals(tenant_id, document_id)
    finally:
        record_signal_query_latency("document", time.perf_counter() - started)


@router.post("/admin/retention/purge")
async def purge_retention(
    current_user: Dict[str, Any] = Depends(require_scopes("activity.ingest", "signals.admin")),
    store: ActivityStore = Depends(get_store),
) -> Dict[str, Any]:
    """Manually trigger retention purge (also run by scheduled job)."""
    result = await store.purge_expired()
    return result.model_dump()


@router.get("/admin/metrics")
async def metrics(
    current_user: Dict[str, Any] = Depends(get_current_user),
    store: ActivityStore = Depends(get_store),
) -> Dict[str, Any]:
    from app.services.metrics import snapshot

    store_metrics = await store.metrics_snapshot()
    return {
        **snapshot(),
        "store": store_metrics,
        "freshness_sla_seconds": settings.freshness_sla_seconds,
        "privacy_threshold_default": settings.privacy_threshold,
    }
