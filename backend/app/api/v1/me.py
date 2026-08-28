"""
/me endpoint: returns current principal info from JWT and allows password changes.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user, get_tenant
from app.services.native_auth import native_auth_service
from app.storage.tenant_db import tenant_db_manager


router = APIRouter(prefix="/me", tags=["me"])


class ChangePasswordRequest(BaseModel):
    """Request to change password."""
    
    old_password: str
    new_password: str


@router.get("")
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Get current principal info from JWT.
    
    Returns:
        Current user information.
    """
    return {
        "principal_id": current_user.get("sub"),
        "tenant_id": current_user.get("tenant_id"),
        "scopes": current_user.get("scopes", []),
        "role": current_user.get("role"),
        "must_change_password": current_user.get("must_change_password", False),
        "iat": current_user.get("iat"),
        "exp": current_user.get("exp"),
    }


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    tenant_routing: dict = Depends(get_tenant),
):
    """
    Change current user's password.
    
    Args:
        request: Old and new passwords
        
    Returns:
        Success message.
        
    Raises:
        HTTPException 401 if old password is incorrect.
        HTTPException 400 if user is SSO-only.
    """
    principal_id = current_user.get("sub")
    tenant_id = tenant_routing.tenant_id
    
    # Get tenant database session
    factory = tenant_db_manager.get_session_factory(
        tenant_routing.db_host,
        tenant_routing.db_name,
        tenant_routing.db_user,
        tenant_routing.db_password,
        tenant_id,
    )
    db_session = factory()
    try:
        await native_auth_service.change_password(
            user_id=principal_id,
            old_password=request.old_password,
            new_password=request.new_password,
            db_session=db_session,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    finally:
        await db_session.close()
    
    return {"message": "Password changed successfully"}
