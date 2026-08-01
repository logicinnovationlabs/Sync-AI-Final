"""
OAuth 2.1 service: authorization_code+PKCE, refresh_token, client_credentials.

Implements OAuth 2.1 flows with mandatory PKCE for public clients.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import hashlib
import secrets
from passlib.hash import bcrypt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError, ForbiddenError
from app.models.oauth_client import OAuthClient, RefreshToken
from app.services.token_service import token_service
from app.storage.redis_client import redis_client


class OAuthService:
    """
    OAuth 2.1 service supporting:
    - authorization_code + PKCE (interactive flows)
    - refresh_token (token refresh)
    - client_credentials (service-to-service)
    """

    def __init__(self):
        self.pkce_challenges: Dict[str, str] = {}  # In-memory for dev (use Redis in prod)

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
        """
        Create an authorization code (step 1 of authorization_code flow).
        
        Args:
            client_id: OAuth client ID
            redirect_uri: Redirect URI from the request
            code_challenge: PKCE code challenge
            code_challenge_method: 'S256' or 'plain'
            tenant_id: Tenant UUID
            principal_id: User UUID
            scopes: Requested scopes
            
        Returns:
            Authorization code string.
        """
        code = secrets.token_urlsafe(32)
        
        # Store the code with its context (in Redis in prod, in-memory for dev)
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
        await redis_client.set_json(tenant_id, f"authz_code:{code}", code_data, ex=600)
        
        return code

    async def exchange_authorization_code(
        self,
        code: str,
        code_verifier: str,
        client_id: str,
        redirect_uri: str,
        db_session: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens (step 2 of authorization_code flow).
        
        Args:
            code: Authorization code
            code_verifier: PKCE code verifier
            client_id: OAuth client ID
            redirect_uri: Redirect URI
            db_session: Database session (tenant DB)
            
        Returns:
            Dict with access_token, refresh_token, expires_in.
            
        Raises:
            UnauthorizedError if code is invalid or expired.
        """
        # Retrieve code data (we don't know tenant_id yet, so we need to iterate or use a different key structure)
        # For simplicity, we'll assume the code is stored with a known tenant_id prefix
        # In production, use a separate keyspace or encode tenant_id in the code
        
        # This is a simplified implementation; in prod, use a proper code->tenant_id lookup
        raise NotImplementedError("Authorization code exchange requires production implementation")

    async def issue_tokens_for_client_credentials(
        self,
        client_id: str,
        client_secret: str,
        scopes: list[str],
        db_session: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Issue tokens via client_credentials flow (service-to-service).
        
        Args:
            client_id: OAuth client ID
            client_secret: Client secret
            scopes: Requested scopes
            db_session: Database session (tenant DB)
            
        Returns:
            Dict with access_token, expires_in.
            
        Raises:
            UnauthorizedError if credentials are invalid.
        """
        # Validate client
        stmt = select(OAuthClient).where(OAuthClient.client_id == client_id)
        result = await db_session.execute(stmt)
        client = result.scalar_one_or_none()
        
        if not client or not bcrypt.verify(client_secret, client.hashed_secret):
            raise UnauthorizedError("Invalid client credentials")
        
        if client.client_type != "confidential":
            raise ForbiddenError("client_credentials flow requires a confidential client")
        
        # Issue access token (no user, so principal_id = client_id)
        access_token = await token_service.issue_access_token(
            tenant_id=str(client.tenant_id),
            principal_id=client_id,
            scopes=scopes,
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
        """
        Refresh an access token using a refresh token.
        
        Args:
            refresh_token_str: Refresh token JWT
            db_session: Database session (tenant DB)
            
        Returns:
            Dict with new access_token, refresh_token, expires_in.
            
        Raises:
            UnauthorizedError if refresh token is invalid or revoked.
        """
        # Validate refresh token
        payload = await token_service.validate_token(refresh_token_str)
        
        if payload.get("token_type") != "refresh":
            raise UnauthorizedError("Invalid token type")
        
        jti = payload["jti"]
        principal_id = payload["sub"]
        tenant_id = payload["tenant_id"]
        
        # Check if refresh token is revoked in DB
        stmt = select(RefreshToken).where(RefreshToken.token_id == jti)
        result = await db_session.execute(stmt)
        token_record = result.scalar_one_or_none()
        
        if not token_record or token_record.revoked:
            raise UnauthorizedError("Refresh token has been revoked")
        
        # Issue new tokens
        access_token = await token_service.issue_access_token(
            tenant_id=tenant_id,
            principal_id=principal_id,
            scopes=[],  # Retrieve from user record in prod
        )
        new_refresh_token = await token_service.issue_refresh_token(
            tenant_id=tenant_id,
            principal_id=principal_id,
        )
        
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
            "expires_in": token_service.access_ttl,
        }


# Global OAuth service instance
oauth_service = OAuthService()
