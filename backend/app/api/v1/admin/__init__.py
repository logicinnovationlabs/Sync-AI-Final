"""Block N admin console — aggregator for org management routes.

Unauthenticated POST /admin/users has been removed. User invite lives at
authenticated POST /api/v1/admin/users (require_admin).

POST /admin/tenants remains first-time bootstrap (chicken-and-egg: no admin
JWT exists until the tenant and first admin are created) and is gated by
X-SnyQ-Setup-Token / TENANT_BOOTSTRAP_TOKEN.
"""

from fastapi import APIRouter

from app.api.v1.admin import audit, connectors, sessions, tenant, users

admin_router = APIRouter(prefix="/admin", tags=["admin"])
admin_router.include_router(users.router)
admin_router.include_router(connectors.router)
admin_router.include_router(audit.router)
admin_router.include_router(sessions.router)
admin_router.include_router(tenant.router)

# Back-compat for any `from app.api.v1.admin import router` callers.
router = admin_router
