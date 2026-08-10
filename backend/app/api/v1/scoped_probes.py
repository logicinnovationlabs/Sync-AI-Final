"""
Scoped probe endpoints for Block A signoff A4/A5.

These expose the scopes named in architecture §24 Block A (search.read,
document.read, admin.audit.read) plus connectors.* already on connectors.py.
Each endpoint requires:
1. Valid JWT (get_current_user)
2. Required scope (require_scope) — A5
3. X-Tenant-ID header matching JWT tenant_id (require_matching_tenant) — A4
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_scope, require_matching_tenant


router = APIRouter(prefix="/scoped", tags=["scoped-probes"])


@router.get(
    "/search",
    summary="Probe endpoint requiring search.read",
    dependencies=[Depends(require_scope("search.read")), Depends(require_matching_tenant)],
)
async def scoped_search(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {"ok": True, "scope": "search.read", "tenant_id": current_user["tenant_id"]}


@router.get(
    "/documents",
    summary="Probe endpoint requiring document.read",
    dependencies=[Depends(require_scope("document.read")), Depends(require_matching_tenant)],
)
async def scoped_documents(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {"ok": True, "scope": "document.read", "tenant_id": current_user["tenant_id"]}


@router.get(
    "/admin/audit",
    summary="Probe endpoint requiring admin.audit.read",
    dependencies=[Depends(require_scope("admin.audit.read")), Depends(require_matching_tenant)],
)
async def scoped_admin_audit(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {"ok": True, "scope": "admin.audit.read", "tenant_id": current_user["tenant_id"]}
