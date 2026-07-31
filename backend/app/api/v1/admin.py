"""
Admin routes: tenant provisioning and user management (dev/test use).
"""

from typing import Optional
from uuid import uuid4, UUID
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.storage.control_plane_db import get_control_plane_session
from app.storage.vault_client import vault_client
from app.storage.tenant_db import tenant_db_manager
from app.services.tenant_resolver import tenant_resolver
from app.services.native_auth import native_auth_service
from app.api.deps import require_scope


router = APIRouter(prefix="/admin", tags=["admin"])


class CreateTenantRequest(BaseModel):
    """Request to create a new tenant."""

    name: str
    subdomain: str
    db_host: str
    db_name: str
    db_user: str
    db_password: str  # Will be stored in Vault, never in DB


class CreateTenantResponse(BaseModel):
    """Response with new tenant details."""

    tenant_id: str
    name: str
    subdomain: str
    db_secret_key: str


class CreateUserRequest(BaseModel):
    """Request to create a new user with email/password."""

    tenant_subdomain: str
    email: EmailStr
    password: str
    display_name: str


class CreateUserResponse(BaseModel):
    """Response with new user details."""

    principal_id: str
    email: str
    display_name: str
    tenant_id: str
    auth_type: str = "native"


@router.post("/tenants", response_model=CreateTenantResponse)
async def create_tenant(
    request: CreateTenantRequest,
    session: AsyncSession = Depends(get_control_plane_session),
):
    """
    Provision a new tenant (dev/test use).
    
    Creates a tenant record in the control-plane DB and stores the password in Vault.
    
    Args:
        request: Tenant creation request
        
    Returns:
        New tenant details (without password).
    """
    tenant_id = uuid4()
    
    # Generate Vault key name (A6: never store password in DB)
    db_secret_key = f"kv/tenant-{tenant_id}/db_password"
    
    # Store password in Vault
    try:
        await vault_client.set_secret(db_secret_key, request.db_password)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store secret in Vault: {e}")
    
    # Create tenant record (no password, only Vault key name)
    tenant = Tenant(
        tenant_id=tenant_id,
        name=request.name,
        subdomain=request.subdomain,
        tenancy_mode="isolated_db",
        config={},
        db_host=request.db_host,
        db_name=request.db_name,
        db_user=request.db_user,
        db_secret_key=db_secret_key,  # A6: Vault key name, not password
    )
    
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    
    return CreateTenantResponse(
        tenant_id=str(tenant.tenant_id),
        name=tenant.name,
        subdomain=tenant.subdomain,
        db_secret_key=tenant.db_secret_key,
    )


@router.post("/users", response_model=CreateUserResponse)
async def create_user(request: CreateUserRequest):
    """
    Create a new user with email/password (admin use).
    
    Creates a native auth user that can log in with email/password.
    
    Args:
        request: User creation request
        
    Returns:
        New user details.
        
    Raises:
        HTTPException 404 if tenant not found.
        HTTPException 400 if user already exists.
    """
    # Resolve tenant by subdomain
    from sqlalchemy import select
    from app.storage.control_plane_db import ControlPlaneSessionLocal
    
    async with ControlPlaneSessionLocal() as control_session:
        stmt = select(Tenant).where(Tenant.subdomain == request.tenant_subdomain)
        result = await control_session.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail=f"Tenant not found: {request.tenant_subdomain}",
            )
        
        tenant_id = tenant.tenant_id
    
    # Resolve tenant routing
    try:
        routing = await tenant_resolver.resolve(str(tenant_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tenant resolution failed: {e}")
    
    # Get tenant database session
    async for db_session in tenant_db_manager.get_session(
        routing.db_host,
        routing.db_name,
        routing.db_user,
        routing.db_password,
        str(tenant_id),
    ):
        # Create user
        try:
            user = await native_auth_service.create_native_user(
                email=request.email,
                password=request.password,
                display_name=request.display_name,
                tenant_id=tenant_id,
                db_session=db_session,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"User creation failed: {e}")
        
        return CreateUserResponse(
            principal_id=str(user.principal_id),
            email=user.email,
            display_name=user.display_name,
            tenant_id=str(user.tenant_id),
        )
