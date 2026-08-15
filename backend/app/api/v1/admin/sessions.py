"""Admin session revocation — bump token_version so JWTs die within 60s."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant, get_tenant_session, require_admin
from app.core.config import settings
from app.models.user import User
from app.services.admin.audit_logger import client_ip, write_audit_log
from app.services.revocation import revocation_service
from app.services.tenant_resolver import TenantRouting
from app.storage.redis_client import redis_client


router = APIRouter(prefix="/sessions", tags=["admin-sessions"])


class RevokeSessionRequest(BaseModel):
    user_id: str


class RevokeSessionResponse(BaseModel):
    user_id: str
    token_version: int
    revoked: bool = True


@router.post("/revoke", response_model=RevokeSessionResponse)
async def revoke_sessions(
    body: RevokeSessionRequest,
    request: Request,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """
    Invalidate all JWTs for ``user_id`` in the admin's tenant.

    Increments ``users.token_version`` and publishes the new version to Redis
    so ``validate_token`` / ``get_current_user`` reject older tokens immediately
    (A2 ≤60s). Also marks refresh tokens revoked when rows exist.
    """
    try:
        tenant_id = UUID(str(tenant.tenant_id))
        actor_id = UUID(str(admin.get("sub")))
        target_id = UUID(str(body.user_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid user_id")

    result = await db_session.execute(
        select(User).where(
            User.principal_id == target_id,
            User.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.token_version = int(user.token_version or 0) + 1
    new_version = user.token_version

    # Redis first so get_current_user sees revoke even if DB commit lags.
    ttl = max(int(settings.token_ttl_access), 60)
    await redis_client.set(
        str(tenant_id),
        f"token_version:{user.principal_id}",
        str(new_version),
        ex=ttl + int(settings.token_ttl_refresh),
    )

    try:
        await revocation_service.revoke_session(
            str(user.principal_id),
            str(tenant_id),
            db_session,
        )
    except Exception:
        # Refresh-token table may be empty for native JWTs; version bump is enough.
        pass

    await write_audit_log(
        db_session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type="session.revoked",
        target={"principal_id": str(user.principal_id), "token_version": new_version},
        ip_address=client_ip(request),
    )
    await db_session.commit()

    return RevokeSessionResponse(
        user_id=str(user.principal_id),
        token_version=new_version,
    )
