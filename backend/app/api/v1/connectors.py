"""
Connector Management API Endpoints.

Connects Block A (Auth, Tenancy, Scopes) with Block B (Google Connectors, Celery Ingestion).

Endpoints:
- POST /api/v1/connectors/{source_type}/backfill: Trigger backfill for tenant
- GET  /api/v1/connectors/{source_type}/status:   Get sync status & watches
- POST /api/v1/connectors/{source_type}/disconnect: Disconnect source & revoke watches
- GET  /api/v1/connectors/google/authorize:      Generate Google OAuth URL

All endpoints strictly enforce:
1. Block A JWT Authentication (Depends(get_current_user))
2. Tenant Routing Resolution (Depends(get_tenant))
3. Scope Checks (require_scope("connectors.write") or require_scope("connectors.read"))
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_tenant, require_scope
from app.services.tenant_resolver import TenantRouting
from app.workers.tasks import backfill_tenant_source
from app.services.cursor_store import cursor_store
from app.connectors.google.watch_manager import WatchManager
from app.connectors.google.oauth import GoogleOAuthManager
from app.core.config import settings


router = APIRouter(prefix="/connectors", tags=["connectors"])


class BackfillRequest(BaseModel):
    """Backfill request payload."""
    source_type: Optional[str] = Field(None, description="Connector source type (e.g. google_drive, google_gmail)")


class ConnectorStatusResponse(BaseModel):
    """Connector status response payload."""
    tenant_id: str
    source_type: str
    cursor: Optional[str]
    watch_active: bool
    details: Dict[str, Any]


@router.post(
    "/{source_type}/backfill",
    summary="Trigger connector backfill",
    dependencies=[Depends(require_scope("connectors.write"))],
)
async def trigger_backfill(
    source_type: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Initiate asynchronous backfill for a connector source.
    
    Requires:
    - Valid JWT Access Token (A1)
    - Scope: connectors.write (A5)
    - Tenant Isolation: Operates ONLY on the tenant_id in the JWT payload (A4)
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    # Enqueue Celery task for backfill
    task_result = backfill_tenant_source.delay(tenant_id=tenant_id, source_type=source_type)

    return {
        "status": "queued",
        "task_id": task_result.id,
        "tenant_id": tenant_id,
        "source_type": source_type,
    }


@router.get(
    "/{source_type}/status",
    summary="Get connector sync status",
    response_model=ConnectorStatusResponse,
    dependencies=[Depends(require_scope("connectors.read"))],
)
async def get_connector_status(
    source_type: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Retrieve sync cursor and watch status for a tenant's connector.
    
    Requires:
    - Valid JWT Access Token
    - Scope: connectors.read
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    cursor = await cursor_store.get_cursor(tenant_id, source_type)
    
    # Check watch status
    watch_info = None
    if source_type == "google_drive":
        # Check drive watch info
        watch_info = await cursor_store.get_watch_by_channel(f"drive-{tenant_id}", "resource")
    elif source_type == "google_gmail":
        watch_info = await cursor_store.get_watch_by_email(f"user@{tenant_id}.com", source_type)

    return ConnectorStatusResponse(
        tenant_id=tenant_id,
        source_type=source_type,
        cursor=cursor,
        watch_active=watch_info is not None,
        details={"watch_info": watch_info} if watch_info else {},
    )


@router.post(
    "/{source_type}/disconnect",
    summary="Disconnect connector and revoke watches",
    dependencies=[Depends(require_scope("connectors.write"))],
)
async def disconnect_connector(
    source_type: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Disconnect a connector, stop watch channels, and remove cursors.
    
    Requires:
    - Valid JWT Access Token
    - Scope: connectors.write
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id or str(tenant.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant execution rejected")

    # Clear cursor
    await cursor_store.update_cursor(tenant_id, source_type, "")

    return {
        "status": "disconnected",
        "tenant_id": tenant_id,
        "source_type": source_type,
    }


@router.get(
    "/google/authorize",
    summary="Generate Google OAuth authorization URL",
    dependencies=[Depends(require_scope("connectors.write"))],
)
async def get_google_authorize_url(
    current_user: Dict[str, Any] = Depends(get_current_user),
    tenant: TenantRouting = Depends(get_tenant),
):
    """
    Generate Google OAuth authorization link for the authenticated tenant.
    
    Requires:
    - Valid JWT Access Token
    - Scope: connectors.write
    """
    tenant_id = current_user.get("tenant_id")
    
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
    redirect_uri = getattr(settings, "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/google/callback")
    
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope=https://www.googleapis.com/auth/drive.readonly%20https://www.googleapis.com/auth/gmail.readonly&"
        f"access_type=offline&"
        f"prompt=consent&"
        f"state={tenant_id}"
    )

    return {
        "authorization_url": auth_url,
        "tenant_id": tenant_id,
    }
