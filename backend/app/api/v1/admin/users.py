"""Admin user lifecycle: invite, list, patch, deactivate, reset password."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant, get_tenant_session, require_admin
from app.models.user import User
from app.services.admin.audit_logger import client_ip, write_audit_log
from app.services.admin.rbac import rbac_service
from app.services.native_auth import native_auth_service
from app.services.password_utils import generate_temporary_password
from app.services.revocation import revocation_service
from app.services.tenant_resolver import TenantRouting


router = APIRouter(prefix="/users", tags=["admin-users"])


class CreateAdminUserRequest(BaseModel):
    email: EmailStr
    display_name: str
    role: str = Field(default="member")


class CreateAdminUserResponse(BaseModel):
    principal_id: str
    email: str
    display_name: str
    tenant_id: str
    role: str
    must_change_password: bool
    temporary_password: str
    auth_type: str = "native"


class UserListItem(BaseModel):
    principal_id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    status: str
    must_change_password: bool
    invited_by: Optional[str] = None


class PatchUserRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


class ResetPasswordResponse(BaseModel):
    principal_id: str
    email: str
    temporary_password: str
    must_change_password: bool = True


class TransferOwnershipRequest(BaseModel):
    target_user_id: str


def _as_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")


def _item(user: User) -> UserListItem:
    return UserListItem(
        principal_id=str(user.principal_id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        status=user.status,
        must_change_password=user.must_change_password,
        invited_by=str(user.invited_by) if user.invited_by else None,
    )


@router.post("", response_model=CreateAdminUserResponse)
async def create_user(
    body: CreateAdminUserRequest,
    request: Request,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """Invite a native user into the admin's tenant. Password is auto-generated."""
    if body.role not in ("owner", "admin", "member", "viewer"):
        raise HTTPException(status_code=400, detail="role must be 'owner', 'admin', 'member', or 'viewer'")

    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    actor_id = _as_uuid(str(admin.get("sub")), "principal_id")
    temp_password = generate_temporary_password()

    # Get actor user for RBAC checks
    actor_result = await db_session.execute(
        select(User).where(
            User.principal_id == actor_id,
            User.tenant_id == tenant_id,
        )
    )
    actor = actor_result.scalar_one_or_none()
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    # RBAC check: can actor grant this role?
    if not rbac_service.can_grant_role(actor.role, body.role):
        raise HTTPException(
            status_code=403,
            detail=f"Users with role '{actor.role}' cannot grant role '{body.role}' to others. "
            f"Only owners can promote users to admin or owner roles."
        )

    try:
        user = await native_auth_service.create_native_user(
            email=str(body.email),
            password=temp_password,
            display_name=body.display_name,
            tenant_id=tenant_id,
            db_session=db_session,
            role=body.role,
            invited_by=actor_id,
            must_change_password=True,
            is_active=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await write_audit_log(
        db_session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type="user.created",
        target={"principal_id": str(user.principal_id), "email": user.email, "role": user.role},
        ip_address=client_ip(request),
    )
    await db_session.commit()

    return CreateAdminUserResponse(
        principal_id=str(user.principal_id),
        email=user.email,
        display_name=user.display_name,
        tenant_id=str(user.tenant_id),
        role=user.role,
        must_change_password=True,
        temporary_password=temp_password,
    )


@router.get("", response_model=List[UserListItem])
async def list_users(
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """List all users in the admin's tenant (never from the request body)."""
    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    result = await db_session.execute(
        select(User)
        .where(User.tenant_id == tenant_id)
        .order_by(User.email)
    )
    return [_item(u) for u in result.scalars().all()]


@router.patch("/{user_id}", response_model=UserListItem)
async def patch_user(
    user_id: str,
    body: PatchUserRequest,
    request: Request,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """Update role or is_active for a user in this tenant."""
    if body.role is None and body.is_active is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    if body.role is not None and body.role not in ("owner", "admin", "member", "viewer"):
        raise HTTPException(status_code=400, detail="role must be 'owner', 'admin', 'member', or 'viewer'")

    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    actor_id = _as_uuid(str(admin.get("sub")), "principal_id")
    target_id = _as_uuid(user_id, "user_id")

    result = await db_session.execute(
        select(User).where(
            User.principal_id == target_id,
            User.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Get actor user for RBAC checks
    actor_result = await db_session.execute(
        select(User).where(
            User.principal_id == actor_id,
            User.tenant_id == tenant_id,
        )
    )
    actor = actor_result.scalar_one_or_none()
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    # RBAC check for role changes
    if body.role is not None and user.role != body.role:
        await rbac_service.check_role_change_permission(
            actor=actor,
            target_user=user,
            new_role=body.role,
            db_session=db_session,
        )

    # RBAC check for deactivation
    if body.is_active is not None and user.is_active != body.is_active and not body.is_active:
        await rbac_service.check_deactivation_permission(
            actor=actor,
            target_user=user,
            db_session=db_session,
        )

    role_changed = body.role is not None and user.role != body.role
    is_active_changed = body.is_active is not None and user.is_active != body.is_active
    
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
        user.status = "active" if body.is_active else "deactivated"

    # If role or is_active changed, revoke all existing sessions
    if role_changed or is_active_changed:
        await revocation_service.revoke_user(
            str(user.principal_id),
            str(tenant_id),
            db_session,
            user,
        )

    await write_audit_log(
        db_session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type="user.updated",
        target={
            "principal_id": str(user.principal_id),
            "role": user.role,
            "is_active": user.is_active,
        },
        ip_address=client_ip(request),
    )
    await db_session.commit()
    await db_session.refresh(user)
    return _item(user)


@router.delete("/{user_id}", response_model=UserListItem)
async def deactivate_user(
    user_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """Soft-delete: deactivate the user. Admins cannot deactivate themselves."""
    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    actor_id = _as_uuid(str(admin.get("sub")), "principal_id")
    target_id = _as_uuid(user_id, "user_id")

    result = await db_session.execute(
        select(User).where(
            User.principal_id == target_id,
            User.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Get actor user for RBAC checks
    actor_result = await db_session.execute(
        select(User).where(
            User.principal_id == actor_id,
            User.tenant_id == tenant_id,
        )
    )
    actor = actor_result.scalar_one_or_none()
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    # RBAC check for deactivation (replaces the simple self-check)
    await rbac_service.check_deactivation_permission(
        actor=actor,
        target_user=user,
        db_session=db_session,
    )

    user.is_active = False
    user.status = "deactivated"

    # Revoke all existing sessions for the deactivated user
    await revocation_service.revoke_user(
        str(user.principal_id),
        str(tenant_id),
        db_session,
        user,
    )

    await write_audit_log(
        db_session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type="user.deactivated",
        target={"principal_id": str(user.principal_id), "email": user.email},
        ip_address=client_ip(request),
    )
    await db_session.commit()
    await db_session.refresh(user)
    return _item(user)


@router.post("/{user_id}/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    user_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """Issue a new temporary password. Returned in the response (email not integrated)."""
    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    actor_id = _as_uuid(str(admin.get("sub")), "principal_id")
    target_id = _as_uuid(user_id, "user_id")

    result = await db_session.execute(
        select(User).where(
            User.principal_id == target_id,
            User.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.password_hash:
        raise HTTPException(status_code=400, detail="Cannot reset password for SSO-only users")

    temp_password = generate_temporary_password()
    user.password_hash = native_auth_service.hash_password(temp_password)
    user.must_change_password = True

    await write_audit_log(
        db_session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type="user.password_reset",
        target={"principal_id": str(user.principal_id)},
        ip_address=client_ip(request),
    )
    await db_session.commit()

    return ResetPasswordResponse(
        principal_id=str(user.principal_id),
        email=user.email,
        temporary_password=temp_password,
    )


@router.post("/transfer-ownership", response_model=UserListItem)
async def transfer_ownership(
    body: TransferOwnershipRequest,
    request: Request,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """
    Transfer ownership from the current owner to a target user.
    
    This is an atomic operation that:
    1. Promotes the target user to owner
    2. Demotes the current owner to admin
    3. Revokes tokens for both users
    4. Writes audit logs
    
    Only the current owner can initiate this transfer.
    """
    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    actor_id = _as_uuid(str(admin.get("sub")), "principal_id")
    target_id = _as_uuid(body.target_user_id, "target_user_id")

    # Get current owner (actor)
    actor_result = await db_session.execute(
        select(User).where(
            User.principal_id == actor_id,
            User.tenant_id == tenant_id,
        )
    )
    current_owner = actor_result.scalar_one_or_none()
    if current_owner is None:
        raise HTTPException(status_code=404, detail="Current owner not found")
    
    # Verify actor is actually the owner
    if current_owner.role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the current owner can transfer ownership"
        )
    
    # Get target user
    target_result = await db_session.execute(
        select(User).where(
            User.principal_id == target_id,
            User.tenant_id == tenant_id,
        )
    )
    target_user = target_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="Target user not found")
    
    # Verify target is not the current owner
    if target_user.principal_id == current_owner.principal_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot transfer ownership to yourself"
        )
    
    # Verify target is active
    if not target_user.is_active or target_user.status != "active":
        raise HTTPException(
            status_code=400,
            detail="Cannot transfer ownership to an inactive user"
        )

    # Atomic ownership transfer within a transaction
    try:
        # Promote target to owner
        target_user.role = "owner"
        
        # Demote current owner to admin
        current_owner.role = "admin"
        
        # Revoke tokens for both users
        await revocation_service.revoke_user(
            str(target_user.principal_id),
            str(tenant_id),
            db_session,
            target_user,
        )
        await revocation_service.revoke_user(
            str(current_owner.principal_id),
            str(tenant_id),
            db_session,
            current_owner,
        )
        
        # Write audit logs
        await write_audit_log(
            db_session,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action_type="ownership.transferred",
            target={
                "from_principal_id": str(current_owner.principal_id),
                "from_email": current_owner.email,
                "to_principal_id": str(target_user.principal_id),
                "to_email": target_user.email,
            },
            ip_address=client_ip(request),
        )
        
        await db_session.commit()
        await db_session.refresh(target_user)
        
        return _item(target_user)
        
    except Exception as e:
        await db_session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Ownership transfer failed: {str(e)}"
        )
