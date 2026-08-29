"""Microsoft Graph change-notification webhook receiver.

Validates subscription handshake + clientState, then enqueues Celery only.
Never fetches Outlook/OneDrive content inside the request handler.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/microsoft", tags=["webhooks"])


@router.api_route("/graph", methods=["GET", "POST"])
async def graph_webhook(
    request: Request,
    validationToken: Optional[str] = Query(None),
):
    # Graph subscription validation handshake
    if validationToken:
        return PlainTextResponse(content=validationToken, status_code=200)

    payload = await request.json()
    notifications = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(notifications, list) or not notifications:
        raise HTTPException(status_code=400, detail="Empty notification payload")

    from app.services.cursor_store import cursor_store
    from app.workers.tasks import process_connector_notification

    accepted = 0
    for note in notifications:
        if not isinstance(note, dict):
            continue
        subscription_id = str(note.get("subscriptionId") or "")
        client_state = str(note.get("clientState") or "")
        if not subscription_id:
            continue

        watch = await cursor_store.get_watch_by_channel(
            channel_id=subscription_id,
            resource_id="onedrive",
        )
        source_type = "onedrive"
        if not watch:
            watch = await cursor_store.get_watch_by_channel(
                channel_id=subscription_id,
                resource_id="outlook",
            )
            source_type = "outlook"
        if not watch:
            logger.warning("Unknown Graph subscription %s", subscription_id)
            continue

        stored_state = (watch.get("watch_data") or {}).get("client_state")
        if stored_state and stored_state != client_state:
            logger.warning("Invalid clientState for subscription %s", subscription_id)
            continue

        tenant_id = str(watch.get("tenant_id") or "")
        # scope_id may be tenant:user — strip for Celery args
        user_id = str((watch.get("watch_data") or {}).get("user_id") or "")
        if ":" in tenant_id and not user_id:
            parts = tenant_id.split(":", 1)
            tenant_id, user_id = parts[0], parts[1]

        _otel_headers: Dict[str, Any] = {}
        TraceContextTextMapPropagator().inject(_otel_headers)
        process_connector_notification.apply_async(
            kwargs={
                "source_type": source_type,
                "tenant_id": tenant_id,
                "user_id": user_id,
            },
            headers=_otel_headers,
        )
        accepted += 1

    if accepted == 0:
        raise HTTPException(status_code=403, detail="No valid notifications")
    return {"status": "accepted", "count": accepted}
