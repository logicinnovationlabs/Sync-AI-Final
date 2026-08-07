"""POST /activity/ingest — activity event ingestion."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_scopes
from app.models.activity import FailedEvent, IngestRequest, IngestResponse
from app.services.activity_store import ActivityStore
from app.services.factory import get_activity_store
from app.services.metrics import record_ingest, record_ingest_latency

logger = logging.getLogger(__name__)
router = APIRouter(tags=["activity"])


def get_store() -> ActivityStore:
    return get_activity_store()


@router.post("/activity/ingest", response_model=IngestResponse)
async def ingest_activity(
    body: IngestRequest,
    current_user: Dict[str, Any] = Depends(require_scopes("activity.ingest")),
    store: ActivityStore = Depends(get_store),
) -> IngestResponse:
    """
    Ingest one or more activity events.

    tenant_id is taken exclusively from the JWT (Block A), never from the body.
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
        except Exception as exc:  # noqa: BLE001
            logger.exception("ingest failed for %s: %s", event.event_id, exc)
            failed.append(FailedEvent(event_id=event.event_id, reason="internal_error"))

    record_ingest(ingested, already, len(failed))
    record_ingest_latency(time.perf_counter() - started)

    status = "accepted" if not failed else ("partial" if ingested or already else "rejected")
    return IngestResponse(
        status=status,
        ingested_count=ingested,
        already_processed_count=already,
        failed_events=failed,
    )
