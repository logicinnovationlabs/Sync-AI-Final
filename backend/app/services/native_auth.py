"""
Native authentication service: email/password authentication.

Complements OIDC/SSO authentication with traditional email/password flows.
Passwords are hashed with bcrypt before storage.
"""

from typing import Optional
from uuid import uuid5, UUID
import logging
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.scim_sync import PRINCIPAL_ID_NAMESPACE
from app.core.exceptions import UnauthorizedError

logger = logging.getLogger(__name__)


class NativeAuthService:
    """
    Service for native email/password authentication.
    
    Handles user creation with passwords and credential verification.
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt.
        """
        pw_bytes = password.encode("utf-8")[:71]
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        Verify a password against its hash.
        """
        pw_bytes = password.encode("utf-8")[:71]
        hash_bytes = password_hash.encode("utf-8")
        try:
            return bcrypt.checkpw(pw_bytes, hash_bytes)
        except Exception:
            return False

    async def authenticate_user(
        self,
        email: str,
        password: str,
        tenant_id: UUID,
        db_session: AsyncSession,
    ) -> User:
        """
        Authenticate a user with email and password.
        
        Args:
            email: User email
            password: Plain text password
            tenant_id: Tenant UUID
            db_session: Database session (tenant DB)
            
        Returns:
            User object if authentication succeeds.
            
        Raises:
            UnauthorizedError if credentials are invalid or user not found.
        """
        # Query user by email and tenant
        stmt = select(User).where(
            User.email == email,
            User.tenant_id == tenant_id,
        )
        result = await db_session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise UnauthorizedError("Invalid email or password")
        
        # Check if user has a password (native auth)
        if not user.password_hash:
            raise UnauthorizedError("User is SSO-only, use OIDC login")
        
        # Verify password
        if not self.verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")
        
        # Check user status (legacy) and Block N is_active flag
        if getattr(user, "is_active", True) is False:
            raise UnauthorizedError("User account is inactive")
        if user.status != "active":
            raise UnauthorizedError(f"User account is {user.status}")
        
        return user

    async def create_native_user(
        self,
        email: str,
        password: str,
        display_name: str,
        tenant_id: UUID,
        db_session: AsyncSession,
        role: str = "member",
        invited_by: Optional[UUID] = None,
        must_change_password: bool = False,
        is_active: bool = True,
    ) -> User:
        """
        Create a new native auth user.
        
        Args:
            email: User email
            password: Plain text password (will be hashed)
            display_name: User's display name
            tenant_id: Tenant UUID
            db_session: Database session (tenant DB)
            role: Org role ('admin' or 'member'). Defaults to member.
            invited_by: principal_id of the inviting admin, if any.
            must_change_password: Force password change on next login.
            is_active: Whether the account can authenticate.
            
        Returns:
            Created User object.
            
        Raises:
            ValueError if user with email already exists.
        """
        if role not in ("owner", "admin", "member", "viewer"):
            raise ValueError("role must be 'owner', 'admin', 'member', or 'viewer'")

        # Check if user already exists
        stmt = select(User).where(
            User.email == email,
            User.tenant_id == tenant_id,
        )
        result = await db_session.execute(stmt)
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            raise ValueError(f"User with email {email} already exists")
        
        # Generate synthetic idp_subject for native users
        idp_subject = f"native:{email}"
        
        # Generate deterministic principal_id (same as SCIM sync)
        principal_id = uuid5(PRINCIPAL_ID_NAMESPACE, idp_subject)
        
        # Hash password
        password_hash = self.hash_password(password)
        
        # Create user
        user = User(
            principal_id=principal_id,
            tenant_id=tenant_id,
            idp_subject=idp_subject,
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            source_profiles={"auth_type": "native"},
            status="active" if is_active else "deactivated",
            role=role,
            invited_by=invited_by,
            must_change_password=must_change_password,
            is_active=is_active,
            token_version=0,
        )
        
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        try:
            from app.storage.canonical_repo import bind_pending_drive_shares

            await bind_pending_drive_shares(
                db_session, tenant_id, user.email, user.principal_id
            )
        except Exception:
            logger.exception(
                "pending identity drain failed at invite email=%s tenant_id=%s",
                user.email,
                tenant_id,
            )
        
        return user

    async def change_password(
        self,
        user_id: UUID,
        old_password: str,
        new_password: str,
        db_session: AsyncSession,
    ) -> None:
        """
        Change a user's password.
        
        Args:
            user_id: User's principal_id
            old_password: Current password (for verification)
            new_password: New password
            db_session: Database session (tenant DB)
            
        Raises:
            UnauthorizedError if old password is incorrect.
            ValueError if user doesn't exist or is SSO-only.
        """
        # Get user
        stmt = select(User).where(User.principal_id == user_id)
        result = await db_session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError("User not found")
        
        if not user.password_hash:
            raise ValueError("Cannot change password for SSO-only users")
        
        # Verify old password
        if not self.verify_password(old_password, user.password_hash):
            raise UnauthorizedError("Current password is incorrect")
        
        # Hash and set new password; clear forced-change flag
        user.password_hash = self.hash_password(new_password)
        user.must_change_password = False
        
        await db_session.commit()


# Global native auth service instance
native_auth_service = NativeAuthService()
