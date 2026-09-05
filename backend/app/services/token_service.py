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

from app.core.backends import mock_backends_allowed
from app.core.config import settings
from app.core.exceptions import InvalidTokenError, RevokedTokenError, UnauthorizedError
from app.core.startup import StartupConfigurationError
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
        # §14.4 key rotation: map of kid -> public PEM; active kid used on issue
        self._public_keys_by_kid: Dict[str, str] = {}
        self._active_kid: str = settings.jwt_active_kid

    def _load_keys(self):
        """Load RSA keys from disk. Ephemeral generation is dev/test only."""
        private_key_path = Path(settings.jwt_private_key_path)
        public_key_path = Path(settings.jwt_public_key_path)

        if self._private_key is None:
            if private_key_path.is_file():
                self._private_key = private_key_path.read_text()
            elif not mock_backends_allowed():
                raise StartupConfigurationError(
                    f"JWT private key missing at {private_key_path}"
                )
            else:
                from cryptography.hazmat.primitives.asymmetric import rsa
                from cryptography.hazmat.primitives import serialization

                private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                self._private_key = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ).decode("utf-8")

                generated_public = private_key.public_key()
                self._public_key = generated_public.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode("utf-8")

        if self._public_key is None:
            if public_key_path.is_file():
                self._public_key = public_key_path.read_text()
            elif not mock_backends_allowed():
                raise StartupConfigurationError(
                    f"JWT public key missing at {public_key_path}"
                )

        # Register active public key under kid for rotation-aware verify
        if self._public_key and self._active_kid not in self._public_keys_by_kid:
            self._public_keys_by_kid[self._active_kid] = self._public_key

    def register_verification_key(self, kid: str, public_pem: str) -> None:
        """
        Register an additional public key for verification (JWT key rotation §14.4).
        Old tokens signed with a previous kid remain verifiable while this key stays registered.
        """
        self._public_keys_by_kid[kid] = public_pem

    def rotate_signing_key(self, new_kid: str, private_pem: str, public_pem: str) -> None:
        """
        Rotate the active signing key without downtime for already-issued tokens.
        New tokens use new_kid; previously registered kids remain valid for verify.
        """
        self._private_key = private_pem
        self._public_key = public_pem
        self._active_kid = new_kid
        self._public_keys_by_kid[new_kid] = public_pem

    async def issue_access_token(
        self,
        tenant_id: str,
        principal_id: str,
        scopes: List[str],
        role: Optional[str] = None,
        token_version: int = 0,
        must_change_password: bool = False,
    ) -> str:
        """
        Issue an RS256 access token.
        
        Args:
            tenant_id: Exactly one tenant UUID (A1)
            principal_id: User/principal UUID
            scopes: List of granted scopes
            role: Optional org role claim (Block N). Always stamped when provided.
            token_version: Snapshot of users.token_version at issue time. Always stamped.
            must_change_password: Hint for the client to force a password change.
            
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
            "token_version": token_version,  # Always stamped for revocation support
        }
        if role is not None:
            payload["role"] = role
            payload["must_change_password"] = must_change_password
        
        token = jwt.encode(
            payload,
            self._private_key,
            algorithm=self.algorithm,
            headers={"kid": self._active_kid},
        )
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
        
        token = jwt.encode(
            payload,
            self._private_key,
            algorithm=self.algorithm,
            headers={"kid": self._active_kid},
        )
        return token

    async def rotate_refresh_token(self, refresh_token: str) -> tuple[str, str]:
        """
        Exchange a refresh JWT for a new access+refresh pair and revoke the old jti.

        Replay of the previous refresh token is rejected by validate_token (A13).
        """
        payload = await self.validate_token(refresh_token)
        if payload.get("token_type") != "refresh":
            raise InvalidTokenError("Invalid token type")
        tenant_id = payload.get("tenant_id")
        principal_id = payload.get("sub")
        if not tenant_id or not principal_id:
            raise InvalidTokenError("Refresh token missing identity")
        jti = payload.get("jti")
        if jti:
            await redis_client.sadd(str(tenant_id), f"revoked:{jti}", jti)
        access = await self.issue_access_token(
            tenant_id=str(tenant_id),
            principal_id=str(principal_id),
            scopes=list(payload.get("scopes") or []),
            role=payload.get("role"),
            token_version=payload.get("token_version", 0),
        )
        new_refresh = await self.issue_refresh_token(str(tenant_id), str(principal_id))
        return access, new_refresh

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

        # Prefer kid-selected public key (§14.4); fall back to active public key
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            verify_key = self._public_keys_by_kid.get(kid) if kid else None
            if verify_key is None:
                verify_key = self._public_key
        except Exception:
            verify_key = self._public_key
        
        try:
            payload = jwt.decode(
                token,
                verify_key,
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

        # Block N: principal-level session revoke via token_version (Redis).
        # Access tokens must have token_version claim; refresh tokens are validated
        # via DB lookup (JTI) and do not require token_version.
        principal_id = payload.get("sub")
        tv_claim = payload.get("token_version")
        token_type = payload.get("token_type")
        
        # Only check token_version for access tokens, not refresh tokens
        # Refresh tokens are revoked via DB lookup of their JTI in RefreshToken table
        if token_type != "refresh":
            if tv_claim is None:
                # Missing token_version claim on access token indicates legacy token or bug - reject
                raise InvalidTokenError("Access token missing required token_version claim")
            
            if tenant_id and principal_id is not None:
                stored = await redis_client.get(tenant_id, f"token_version:{principal_id}")
                # If Redis is unavailable (stored is None due to connection failure),
                # we fail closed to prevent revocation bypass. The redis_client has
                # fallback behavior, but for security-critical revocation checks we
                # require actual Redis connectivity.
                if stored is None:
                    # Check if Redis client is actually connected (not using fallback)
                    from app.storage.redis_client import redis_client as rc
                    if rc._client is None:
                        raise InvalidTokenError("Redis unavailable - cannot verify token revocation status")
                else:
                    try:
                        if int(stored) > int(tv_claim):
                            raise RevokedTokenError(str(jti or principal_id))
                    except (TypeError, ValueError):
                        pass
        
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
