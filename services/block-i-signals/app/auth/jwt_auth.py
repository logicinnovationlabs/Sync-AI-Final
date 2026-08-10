"""JWT auth dependencies (Block A integration surface)."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

DEFAULT_SCOPES = ["activity.ingest", "signals.read"]


def _decode_jwt_payload_unverified(token: str) -> Dict[str, Any]:
    """Decode JWT payload without signature verification (dev/test stub)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Not a JWT")
    payload = parts[1]
    payload += "=" * (4 - len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload)
    data = json.loads(decoded)
    # Normalize principal claim
    if "principal_id" not in data and "sub" in data:
        data["principal_id"] = data["sub"]
    return data


def _verify_with_key(token: str) -> Optional[Dict[str, Any]]:
    """Attempt real RS256 verification when a public key is configured."""
    if not settings.jwt_public_key_path:
        return None
    try:
        import jwt
        from pathlib import Path

        key = Path(settings.jwt_public_key_path).read_text(encoding="utf-8")
        data = jwt.decode(token, key, algorithms=["RS256"])
        if "principal_id" not in data and "sub" in data:
            data["principal_id"] = data["sub"]
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("JWT key verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token signature") from exc


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    """
    Resolve caller identity from Bearer JWT.

    Production path: Block A signature verification via jwt_public_key_path.
    Test/dev path: decode payload without verification (matches Blocks F/H stub).
    """
    if credentials is None or not credentials.credentials:
        if settings.environment == "test":
            return {
                "tenant_id": "tenant-a",
                "principal_id": "p-user-alice",
                "scopes": list(DEFAULT_SCOPES),
            }
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = credentials.credentials
    if settings.jwt_public_key_path:
        verified = _verify_with_key(token)
        if verified is not None:
            return verified

    try:
        return _decode_jwt_payload_unverified(token)
    except Exception:
        if settings.environment == "test" and len(token) >= 8:
            return {
                "tenant_id": "tenant-a",
                "principal_id": "p-user-alice",
                "scopes": list(DEFAULT_SCOPES),
            }
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_tenant(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> str:
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id missing from token")
    return str(tenant_id)


def assert_tenant_binding(request_tenant_id: str, token_tenant_id: str) -> None:
    """Reject cross-tenant requests when isolation is enforced."""
    if not settings.enforce_tenant_isolation:
        return
    if request_tenant_id != token_tenant_id:
        raise HTTPException(
            status_code=403,
            detail="TENANT ISOLATION VIOLATION: request tenant_id does not match token",
        )


def require_scopes(*required: str):
    """FastAPI dependency factory: require at least one of the listed scopes."""

    async def _check(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        scopes: List[str] = list(current_user.get("scopes") or [])
        if isinstance(current_user.get("scope"), str):
            scopes.extend(current_user["scope"].split())
        if not required:
            return current_user
        if not any(s in scopes for s in required):
            raise HTTPException(
                status_code=403,
                detail=f"Missing required scope(s): {', '.join(required)}",
            )
        return current_user

    return _check
