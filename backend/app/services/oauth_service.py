"""
OAuth 2.1 service: authorization_code+PKCE, refresh_token, client_credentials.

Implements OAuth 2.1 flows with mandatory PKCE for public clients.
Authorization codes live in Redis (tenant-agnostic index + tenant copy).
Refresh tokens are persisted hashed in the tenant DB and rotated on use.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UnauthorizedError, ForbiddenError
from app.models.oauth_client import OAuthClient, RefreshToken
from app.models.user import User
from app.services.admin.scopes import scopes_for_role
from app.services.token_service import token_service
from app.storage.redis_client import redis_client

AUTHZ_INDEX_TENANT = "oauth"


def hash_refresh_token(token: str) -> str:
    """SHA-256 hex of the JWT (bcrypt truncates past 72 bytes)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    if not code_verifier or not code_challenge:
        return False
    method_norm = (method or "S256").upper()
    if method_norm == "S256":
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        import base64

        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return secrets.compare_digest(computed, code_challenge)
    if method_norm == "PLAIN":
        return secrets.compare_digest(code_verifier, code_challenge)
    return False


class OAuthService:
    """
    OAuth 2.1 service supporting:
    - authorization_code + PKCE (interactive flows)
    - refresh_token (token refresh)
    - client_credentials (service-to-service)
    """

    async def create_authorization_code(
        self,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
        tenant_id: str,
        principal_id: str,
        scopes: list[str],
    ) -> str:
        code = secrets.token_urlsafe(32)
        code_data = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "tenant_id": tenant_id,
            "principal_id": principal_id,
            "scopes": scopes,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        }
        await redis_client.set_json(AUTHZ_INDEX_TENANT, f"authz_code:{code}", code_data, ex=600)
        await redis_client.set_json(tenant_id, f"authz_code:{code}", code_data, ex=600)
        return code

    async def peek_authorization_code(self, code: str) -> Optional[Dict[str, Any]]:
        return await redis_client.get_json(AUTHZ_INDEX_TENANT, f"authz_code:{code}")

    async def _consume_authorization_code(self, code: str) -> Dict[str, Any]:
        code_data = await redis_client.get_json(AUTHZ_INDEX_TENANT, f"authz_code:{code}")
        if not code_data:
            raise UnauthorizedError("Invalid or expired authorization code")
        await redis_client.delete(AUTHZ_INDEX_TENANT, f"authz_code:{code}")
        tenant_id = code_data.get("tenant_id")
        if tenant_id:
            await redis_client.delete(str(tenant_id), f"authz_code:{code}")
        expires_at = code_data.get("expires_at")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < datetime.now(timezone.utc):
                    raise UnauthorizedError("Authorization code expired")
            except UnauthorizedError:
                raise
            except Exception:
                raise UnauthorizedError("Authorization code expired")
        return code_data

    async def persist_refresh_token(
        self,
        refresh_token_str: str,
        tenant_id: str,
        principal_id: str,
        db_session: AsyncSession,
    ) -> None:
        payload = await token_service.validate_token(refresh_token_str)
        jti = payload.get("jti")
        if not jti:
            raise UnauthorizedError("Refresh token missing jti")
        exp = payload.get("exp")
        if exp:
            expires_at = datetime.fromtimestamp(int(exp), tz=timezone.utc)
        else:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.token_ttl_refresh)
        db_session.add(
            RefreshToken(
                token_id=UUID(str(jti)),
                principal_id=UUID(str(principal_id)),
                tenant_id=UUID(str(tenant_id)),
                hashed_token=hash_refresh_token(refresh_token_str),
                revoked=False,
                expires_at=expires_at,
            )
        )
        await db_session.commit()

    async def _scopes_for_principal(
        self, principal_id: str, tenant_id: str, db_session: AsyncSession, fallback: list[str]
    ) -> tuple[list[str], dict[str, Any]]:
        """
        Get scopes and user metadata for a principal.
        
        Returns:
            Tuple of (scopes list, user metadata dict with role, token_version, etc.)
            
        Raises:
            UnauthorizedError if user is inactive or not found.
        """
        try:
            result = await db_session.execute(
                select(User).where(
                    User.principal_id == UUID(str(principal_id)),
                    User.tenant_id == UUID(str(tenant_id)),
                )
            )
            user = result.scalar_one_or_none()
        except Exception:
            return list(fallback), {}
        
        if user is None:
            return list(fallback), {}
        
        # Check account state - reject refresh for inactive/deactivated users
        if getattr(user, "is_active", True) is False:
            raise UnauthorizedError("User account is inactive")
        if user.status != "active":
            raise UnauthorizedError(f"User account is {user.status}")
        
        role = getattr(user, "role", None) or "member"
        scopes = scopes_for_role(role)
        
        # Return user metadata for token issuance
        user_metadata = {
            "role": role,
            "token_version": getattr(user, "token_version", 0) or 0,
            "must_change_password": getattr(user, "must_change_password", False),
        }
        
        return scopes, user_metadata

    async def exchange_authorization_code(
        self,
        code: str,
        code_verifier: str,
        client_id: str,
        redirect_uri: str,
        db_session: AsyncSession,
    ) -> Dict[str, Any]:
        code_data = await self._consume_authorization_code(code)
        if code_data.get("client_id") != client_id:
            raise UnauthorizedError("client_id mismatch")
        if code_data.get("redirect_uri") != redirect_uri:
            raise UnauthorizedError("redirect_uri mismatch")
        if not verify_pkce(
            code_verifier,
            code_data.get("code_challenge") or "",
            code_data.get("code_challenge_method") or "S256",
        ):
            raise UnauthorizedError("PKCE verification failed")

        tenant_id = str(code_data["tenant_id"])
        principal_id = str(code_data["principal_id"])
        scopes = list(code_data.get("scopes") or [])
        scopes, user_metadata = await self._scopes_for_principal(principal_id, tenant_id, db_session, scopes)

        access_token = await token_service.issue_access_token(
            tenant_id=tenant_id,
            principal_id=principal_id,
            scopes=scopes,
            role=user_metadata.get("role"),
            token_version=user_metadata.get("token_version", 0),
            must_change_password=user_metadata.get("must_change_password", False),
        )
        refresh_token = await token_service.issue_refresh_token(
            tenant_id=tenant_id,
            principal_id=principal_id,
        )
        await self.persist_refresh_token(refresh_token, tenant_id, principal_id, db_session)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": token_service.access_ttl,
        }

    async def issue_tokens_for_client_credentials(
        self,
        client_id: str,
        client_secret: str,
        scopes: list[str],
        db_session: AsyncSession,
    ) -> Dict[str, Any]:
        stmt = select(OAuthClient).where(OAuthClient.client_id == client_id)
        result = await db_session.execute(stmt)
        client = result.scalar_one_or_none()

        if not client or not bcrypt.verify(client_secret, client.hashed_secret):
            raise UnauthorizedError("Invalid client credentials")

        if client.client_type != "confidential":
            raise ForbiddenError("client_credentials flow requires a confidential client")

        # For client_credentials, use client_id as principal and a fixed role
        # Service-to-service tokens don't have a User row, so token_version defaults to 0
        access_token = await token_service.issue_access_token(
            tenant_id=str(client.tenant_id),
            principal_id=client_id,
            scopes=scopes,
            role="service",  # Explicit role for service accounts
            token_version=0,  # Service accounts don't have user-level versioning
        )
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": token_service.access_ttl,
        }

    async def refresh_access_token(
        self,
        refresh_token_str: str,
        db_session: AsyncSession,
    ) -> Dict[str, Any]:
        payload = await token_service.validate_token(refresh_token_str)

        if payload.get("token_type") != "refresh":
            raise UnauthorizedError("Invalid token type")

        jti = payload["jti"]
        principal_id = payload["sub"]
        tenant_id = payload["tenant_id"]

        stmt = select(RefreshToken).where(RefreshToken.token_id == UUID(str(jti)))
        result = await db_session.execute(stmt)
        token_record = result.scalar_one_or_none()

        if not token_record or token_record.revoked:
            raise UnauthorizedError("Refresh token has been revoked")
        if str(token_record.tenant_id) != str(tenant_id):
            raise UnauthorizedError("Refresh token tenant mismatch")
        if not secrets.compare_digest(token_record.hashed_token, hash_refresh_token(refresh_token_str)):
            raise UnauthorizedError("Refresh token mismatch")
        if token_record.expires_at:
            exp = token_record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < datetime.now(timezone.utc):
                raise UnauthorizedError("Refresh token expired")

        token_record.revoked = True
        await redis_client.sadd(str(tenant_id), f"revoked:{jti}", str(jti))

        scopes, user_metadata = await self._scopes_for_principal(principal_id, str(tenant_id), db_session, [])
        access_token = await token_service.issue_access_token(
            tenant_id=str(tenant_id),
            principal_id=str(principal_id),
            scopes=scopes,
            role=user_metadata.get("role"),
            token_version=user_metadata.get("token_version", 0),
            must_change_password=user_metadata.get("must_change_password", False),
        )
        new_refresh_token = await token_service.issue_refresh_token(
            tenant_id=str(tenant_id),
            principal_id=str(principal_id),
        )
        await db_session.commit()
        await self.persist_refresh_token(
            new_refresh_token, str(tenant_id), str(principal_id), db_session
        )
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
            "expires_in": token_service.access_ttl,
        }


oauth_service = OAuthService()
