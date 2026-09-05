"""Admin document access control endpoints.

Provides owner/admin roles with visibility and control over per-document
access overrides for members in their tenant.
"""

from __future__ import annotations

from typing import List, Optional, Set, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant, get_tenant_session, require_admin
from app.models.user import User
from app.models.canonical import ACLEntryRow, CanonicalDocumentRow, IdentityGroupRow
from app.models.admin_access_override import AdminAccessOverride
from app.models.tenant_connector import TenantConnector
from app.services.admin.audit_logger import client_ip, write_audit_log
from app.services.tenant_resolver import TenantRouting


router = APIRouter(prefix="/members", tags=["admin-document-access"])


class MemberListItem(BaseModel):
    """Member in the tenant with owned vs ACL-shared document counts."""
    principal_id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    status: str
    document_count: int = 0
    owned_count: int = 0
    shared_count: int = 0
    connector_connected: bool = False


class DocumentListItem(BaseModel):
    """Document this member owns or can read via ACL, plus override status."""
    document_id: str
    title: str
    source_type: str
    owner_principal_id: Optional[str] = None
    created_at: str
    access_override: Optional[str] = None  # "allow", "deny", or None (default)
    assignment: str = "owned"  # "owned" or "shared"


class SetAccessOverrideRequest(BaseModel):
    """Request to set an access override."""
    access: str = Field(..., description="Access type: 'allow' or 'deny'")


def _as_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")


def _principal_in_group(member_ids: object, principal_id: UUID) -> bool:
    if not member_ids:
        return False
    wanted = {str(principal_id), str(principal_id).lower()}
    for raw in member_ids:
        if str(raw) in wanted:
            return True
    return False


async def _owned_and_shared_ids(
    db_session: AsyncSession,
    tenant_id: UUID,
    principal_id: UUID,
) -> Tuple[Set[str], Set[str]]:
    """Return (owned_document_ids, acl-shared document ids not already owned)."""
    owned_result = await db_session.execute(
        select(CanonicalDocumentRow.id).where(
            CanonicalDocumentRow.tenant_id == tenant_id,
            CanonicalDocumentRow.owner_principal_id == principal_id,
        )
    )
    owned_ids = {row[0] for row in owned_result.all()}

    direct_acl = await db_session.execute(
        select(ACLEntryRow.document_id).where(
            ACLEntryRow.tenant_id == tenant_id,
            ACLEntryRow.principal_id == principal_id,
            ACLEntryRow.is_deny.is_(False),
        )
    )
    shared_ids = {row[0] for row in direct_acl.all()}

    groups_result = await db_session.execute(
        select(IdentityGroupRow).where(IdentityGroupRow.tenant_id == tenant_id)
    )
    group_ids = [
        group.id
        for group in groups_result.scalars().all()
        if _principal_in_group(group.member_principal_ids, principal_id)
    ]
    if group_ids:
        group_acl = await db_session.execute(
            select(ACLEntryRow.document_id).where(
                ACLEntryRow.tenant_id == tenant_id,
                ACLEntryRow.group_id.in_(group_ids),
                ACLEntryRow.is_deny.is_(False),
            )
        )
        shared_ids.update(row[0] for row in group_acl.all())

    shared_ids -= owned_ids
    return owned_ids, shared_ids


@router.get("", response_model=List[MemberListItem])
async def list_members(
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """
    List all members in the admin's tenant with connection status and document count.
    
    Returns:
        List of members with their role, active status, document count,
        and connector connection status.
    """
    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    
    # Get all users in the tenant
    result = await db_session.execute(
        select(User)
        .where(User.tenant_id == tenant_id)
        .order_by(User.email)
    )
    users = result.scalars().all()

    org_row = await db_session.execute(
        select(TenantConnector.id).where(
            TenantConnector.tenant_id == tenant_id,
            TenantConnector.connection_scope == "organization",
            TenantConnector.credential_ref.isnot(None),
            TenantConnector.source_type.in_(("google_drive", "google_gmail", "sharepoint")),
        ).limit(1)
    )
    org_connector_connected = org_row.scalar_one_or_none() is not None

    members = []
    for user in users:
        owned_ids, shared_ids = await _owned_and_shared_ids(
            db_session, tenant_id, user.principal_id
        )
        owned_count = len(owned_ids)
        shared_count = len(shared_ids)
        members.append(MemberListItem(
            principal_id=str(user.principal_id),
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            is_active=user.is_active,
            status=user.status,
            document_count=owned_count + shared_count,
            owned_count=owned_count,
            shared_count=shared_count,
            connector_connected=org_connector_connected,
        ))
    
    return members


@router.get("/{user_id}/documents", response_model=List[DocumentListItem])
async def list_member_documents(
    user_id: str,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """
    List documents this member owns or can read via ACL (direct or group).

    Each row is tagged assignment=owned|shared and includes the admin override.
    """
    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    target_user_id = _as_uuid(user_id, "user_id")
    
    user_result = await db_session.execute(
        select(User).where(
            User.principal_id == target_user_id,
            User.tenant_id == tenant_id,
        )
    )
    target_user = user_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    owned_ids, shared_ids = await _owned_and_shared_ids(
        db_session, tenant_id, target_user_id
    )
    all_ids = owned_ids | shared_ids
    if not all_ids:
        return []

    doc_result = await db_session.execute(
        select(CanonicalDocumentRow)
        .where(
            CanonicalDocumentRow.tenant_id == tenant_id,
            CanonicalDocumentRow.id.in_(all_ids),
        )
        .order_by(CanonicalDocumentRow.created_at.desc())
    )
    documents = doc_result.scalars().all()
    
    override_result = await db_session.execute(
        select(AdminAccessOverride)
        .where(
            AdminAccessOverride.tenant_id == tenant_id,
            AdminAccessOverride.target_user_id == target_user_id
        )
    )
    override_map = {override.document_id: override.access for override in override_result.scalars().all()}
    
    items = []
    for doc in documents:
        items.append(DocumentListItem(
            document_id=doc.id,
            title=doc.title,
            source_type=doc.source_type,
            owner_principal_id=str(doc.owner_principal_id) if doc.owner_principal_id else None,
            created_at=doc.created_at.isoformat() if doc.created_at else "",
            access_override=override_map.get(doc.id),
            assignment="owned" if doc.id in owned_ids else "shared",
        ))
    
    return items


@router.post("/{user_id}/documents/{document_id}/access")
async def set_access_override(
    user_id: str,
    document_id: str,
    body: SetAccessOverrideRequest,
    request: Request,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """
    Set an access override for a member on a specific document.
    
    Validates:
    - Admin and target member are in the same tenant as the document
    - Admin has legitimate access to grant (tenant boundary enforcement)
    - Access type is valid (allow/deny)
    """
    if body.access not in ("allow", "deny"):
        raise HTTPException(status_code=400, detail="access must be 'allow' or 'deny'")
    
    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    target_user_id = _as_uuid(user_id, "user_id")
    admin_id = _as_uuid(str(admin.get("sub")), "principal_id")
    
    # Verify target user exists in the same tenant
    user_result = await db_session.execute(
        select(User).where(
            User.principal_id == target_user_id,
            User.tenant_id == tenant_id,
        )
    )
    target_user = user_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found in this tenant")
    
    # Verify document exists in the same tenant
    doc_result = await db_session.execute(
        select(CanonicalDocumentRow).where(
            CanonicalDocumentRow.id == document_id,
            CanonicalDocumentRow.tenant_id == tenant_id,
        )
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found in this tenant")
    
    # Verify admin exists and has owner/admin role (already checked by require_admin)
    admin_result = await db_session.execute(
        select(User).where(
            User.principal_id == admin_id,
            User.tenant_id == tenant_id,
        )
    )
    admin_user = admin_result.scalar_one_or_none()
    if admin_user is None:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    # Check if override already exists
    existing_result = await db_session.execute(
        select(AdminAccessOverride).where(
            AdminAccessOverride.tenant_id == tenant_id,
            AdminAccessOverride.document_id == document_id,
            AdminAccessOverride.target_user_id == target_user_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        # Update existing override
        existing.access = body.access
        existing.set_by_admin_id = admin_id
    else:
        # Create new override
        new_override = AdminAccessOverride(
            tenant_id=tenant_id,
            document_id=document_id,
            target_user_id=target_user_id,
            access=body.access,
            set_by_admin_id=admin_id,
        )
        db_session.add(new_override)
    
    # Write audit log
    await write_audit_log(
        db_session,
        tenant_id=tenant_id,
        actor_id=admin_id,
        action_type="admin_access_override.set",
        target={
            "document_id": document_id,
            "target_user_id": str(target_user_id),
            "access": body.access,
        },
        ip_address=client_ip(request),
    )
    
    await db_session.commit()
    
    return {"message": "Access override set successfully"}


@router.delete("/{user_id}/documents/{document_id}/access")
async def remove_access_override(
    user_id: str,
    document_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
    tenant: TenantRouting = Depends(get_tenant),
    db_session: AsyncSession = Depends(get_tenant_session),
):
    """
    Remove an access override, reverting to default ACL behavior.
    
    Validates tenant boundaries before removal.
    """
    tenant_id = _as_uuid(str(tenant.tenant_id), "tenant_id")
    target_user_id = _as_uuid(user_id, "user_id")
    admin_id = _as_uuid(str(admin.get("sub")), "principal_id")
    
    # Verify target user exists in the same tenant
    user_result = await db_session.execute(
        select(User).where(
            User.principal_id == target_user_id,
            User.tenant_id == tenant_id,
        )
    )
    target_user = user_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found in this tenant")
    
    # Verify document exists in the same tenant
    doc_result = await db_session.execute(
        select(CanonicalDocumentRow).where(
            CanonicalDocumentRow.id == document_id,
            CanonicalDocumentRow.tenant_id == tenant_id,
        )
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found in this tenant")
    
    # Find and delete the override
    override_result = await db_session.execute(
        select(AdminAccessOverride).where(
            AdminAccessOverride.tenant_id == tenant_id,
            AdminAccessOverride.document_id == document_id,
            AdminAccessOverride.target_user_id == target_user_id,
        )
    )
    override = override_result.scalar_one_or_none()
    
    if override is None:
        raise HTTPException(status_code=404, detail="Access override not found")
    
    await db_session.delete(override)
    
    # Write audit log
    await write_audit_log(
        db_session,
        tenant_id=tenant_id,
        actor_id=admin_id,
        action_type="admin_access_override.removed",
        target={
            "document_id": document_id,
            "target_user_id": str(target_user_id),
        },
        ip_address=client_ip(request),
    )
    
    await db_session.commit()
    
    return {"message": "Access override removed successfully"}
