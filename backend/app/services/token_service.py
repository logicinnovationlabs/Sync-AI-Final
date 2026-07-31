"""
TokenService: JWT issuance and validation (RS256).

Critical for Signoff A1: every JWT contains exactly one tenant_id claim.
Critical for Signoff A2, A4: revocation and cross-tenant replay rejection.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from uuid import uuid4
import jwt
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import InvalidTokenError, RevokedTokenError, UnauthorizedError
from app.storage.redis_client import redis_client


class TokenService:
    """
    JWT token issuance and validation using RS256.
    
    Every token contains exactly one tenant_id claim (A1).
    """

    def __init__(self):
        self.algorithm = settings.jwt_algorithm
        self.issuer = settings.jwt_issuer
        self.access_ttl = settings.token_ttl_access
        self.refresh_ttl = settings.token_ttl_refresh
        self._private_key: Optional[str] = None
        self._public_key: Optional[str] = None

    def _load_keys(self):
        """Load RSA keys from disk (lazy loading)."""
        if self._private_key is None:
            private_key_path = Path(settings.jwt_private_key_path)
            if private_key_path.exists():
                self._private_key = private_key_path.read_text()
            else:
                # Generate keys on the fly for dev (not production!)
                from cryptography.hazmat.primitives.asymmetric import rsa
                from cryptography.hazmat.primitives import serialization

                private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                self._private_key = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ).decode("utf-8")

                public_key = private_key.public_key()
                self._public_key = public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode("utf-8")
        
        if self._public_key is None:
            public_key_path = Path(settings.jwt_public_key_path)
            if public_key_path.exists():
                self._public_key = public_key_path.read_text()

    async def issue_access_token(
        self,
        tenant_id: str,
        principal_id: str,
        scopes: List[str],
    ) -> str:
        """
        Issue an RS256 access token.
        
        Args:
            tenant_id: Exactly one tenant UUID (A1)
            principal_id: User/principal UUID
            scopes: List of granted scopes
            
        Returns:
            Signed JWT string.
        """
        self._load_keys()
        
        now = datetime.now(timezone.utc)
        jti = str(uuid4())
        
        payload = {
            "iss": self.issuer,
            "sub": principal_id,
            "tenant_id": tenant_id,  # A1: exactly one tenant_id
            "scopes": scopes,
            "iat": now,
            "exp": now + timedelta(seconds=self.access_ttl),
            "jti": jti,
        }
        
        token = jwt.encode(payload, self._private_key, algorithm=self.algorithm)
        return token

    async def issue_refresh_token(
        self,
        tenant_id: str,
        principal_id: str,
    ) -> str:
        """
        Issue a refresh token (longer TTL, fewer scopes).
        
        Args:
            tenant_id: Tenant UUID
            principal_id: User UUID
            
        Returns:
            Signed JWT refresh token.
        """
        self._load_keys()
        
        now = datetime.now(timezone.utc)
        jti = str(uuid4())
        
        payload = {
            "iss": self.issuer,
            "sub": principal_id,
            "tenant_id": tenant_id,
            "token_type": "refresh",
            "iat": now,
            "exp": now + timedelta(seconds=self.refresh_ttl),
            "jti": jti,
        }
        
        token = jwt.encode(payload, self._private_key, algorithm=self.algorithm)
        return token

    async def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate and decode a JWT.
        
        Args:
            token: JWT string
            
        Returns:
            Decoded token payload.
            
        Raises:
            InvalidTokenError if signature/expiry invalid.
            RevokedTokenError if token has been revoked (A2).
        """
        self._load_keys()
        
        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[self.algorithm],
                issuer=self.issuer,
            )
        except jwt.ExpiredSignatureError:
            raise InvalidTokenError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token: {e}")
        
        # Check revocation (A2: must be rejected within 60s)
        jti = payload.get("jti")
        tenant_id = payload.get("tenant_id")
        if jti and tenant_id:
            revoked = await redis_client.sismember(tenant_id, f"revoked:{jti}", jti)
            if revoked:
                raise RevokedTokenError(jti)
        
        # A1: Ensure exactly one tenant_id
        if "tenant_id" not in payload:
            raise InvalidTokenError("Token missing tenant_id claim")
        
        return payload

    async def decode_without_validation(self, token: str) -> Dict[str, Any]:
        """
        Decode a token without validation (for introspection only).
        
        Args:
            token: JWT string
            
        Returns:
            Decoded payload (unverified).
        """
        return jwt.decode(token, options={"verify_signature": False})


# Global token service instance
token_service = TokenService()
