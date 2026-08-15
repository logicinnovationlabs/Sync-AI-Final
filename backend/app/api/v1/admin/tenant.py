"""First-time tenant bootstrap (unauthenticated by design)."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog  # noqa: F401 — register metadata
from app.models.base import Base
from app.models.tenant import Tenant
from app.models.tenant_connector import TenantConnector  # noqa: F401
from app.models.user import User  # noqa: F401
from app.services.native_auth import native_auth_service
from app.services.password_utils import generate_temporary_password
from app.services.tenant_resolver import tenant_resolver
from app.storage.control_plane_db import get_control_plane_session
from app.storage.tenant_db import tenant_db_manager
from app.storage.vault_client import vault_client

router = APIRouter(tags=["admin"])


class CreateTenantRequest(BaseModel):
    """Bootstrap a tenant and its first Full Admin (Glean-style setup)."""

    name: str
    subdomain: str
    db_host: str
    db_name: str
    db_user: str
    db_password: str  # Stored in Vault, never in DB
    admin_email: EmailStr
    admin_display_name: str


class CreateTenantResponse(BaseModel):
    tenant_id: str
    name: str
    subdomain: str
    db_secret_key: str
    admin_principal_id: str
    admin_email: str
    temporary_password: str


@router.post("/tenants", response_model=CreateTenantResponse)
async def create_tenant(
    request: CreateTenantRequest,
    session: AsyncSession = Depends(get_control_plane_session),
):
    """
    First-time tenant bootstrap (dev/test and initial setup).

    Unauthenticated on purpose: no admin JWT exists until the tenant and
    first admin are created (chicken-and-egg).
    """
    tenant_id = uuid4()
    db_secret_key = f"kv/tenant-{tenant_id}/db_password"

    try:
        await vault_client.set_secret(db_secret_key, request.db_password)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store secret in Vault: {e}")

    tenant = Tenant(
        tenant_id=tenant_id,
        name=request.name,
        subdomain=request.subdomain,
        tenancy_mode="isolated_db",
        config={},
        db_host=request.db_host,
        db_name=request.db_name,
        db_user=request.db_user,
        db_secret_key=db_secret_key,
    )
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    try:
        routing = await tenant_resolver.resolve(str(tenant.tenant_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tenant resolution failed: {e}")

    engine = tenant_db_manager.get_engine(
        routing.db_host,
        routing.db_name,
        routing.db_user,
        routing.db_password,
        str(tenant.tenant_id),
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    temp_password = generate_temporary_password()
    admin_user = None
    async for db_session in tenant_db_manager.get_session(
        routing.db_host,
        routing.db_name,
        routing.db_user,
        routing.db_password,
        str(tenant.tenant_id),
    ):
        try:
            admin_user = await native_auth_service.create_native_user(
                email=str(request.admin_email),
                password=temp_password,
                display_name=request.admin_display_name,
                tenant_id=tenant.tenant_id,
                db_session=db_session,
                role="admin",
                invited_by=None,
                must_change_password=True,
                is_active=True,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"First admin creation failed: {e}")

    if admin_user is None:
        raise HTTPException(status_code=500, detail="First admin creation failed")

    return CreateTenantResponse(
        tenant_id=str(tenant.tenant_id),
        name=tenant.name,
        subdomain=tenant.subdomain,
        db_secret_key=tenant.db_secret_key,
        admin_principal_id=str(admin_user.principal_id),
        admin_email=admin_user.email,
        temporary_password=temp_password,
    )
