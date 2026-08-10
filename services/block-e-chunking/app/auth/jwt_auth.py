"""JWT auth dependencies — Block A integration surface.

Validates Bearer JWTs using Block A's RS256 public key (same verification
path as backend TokenService.validate_token signature check). Optional HTTP
validate URL if Block A exposes one via BLOCK_A_TOKEN_VALIDATE_URL.

Block A does not currently expose a dedicated HTTP introspect route; cryptographic
verification against JWT_PUBLIC_KEY_PATH is the cross-block contract used by
Blocks F/G/H/I/J.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


def _public_key_path() -> Optional[Path]:
    raw = (os.environ.get("JWT_PUBLIC_KEY_PATH") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return p
    backend = Path(r"D:\PROJECTS\Sync Ai Final\backend")
    candidates = [
        p,
        backend / raw,
        backend / raw.lstrip("./"),
        Path.cwd() / raw,
    ]
    for c in candidates:
        if c.exists():
            return c
    return p


def _verify_with_block_a_key(token: str) -> Dict[str, Any]:
    import jwt

    key_path = _public_key_path()
    if key_path is None or not key_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Block A JWT public key not configured (JWT_PUBLIC_KEY_PATH)",
        )
    key = key_path.read_text(encoding="utf-8")
    issuer = os.environ.get("JWT_ISSUER", "snyq-platform")
    algorithms = [os.environ.get("JWT_ALGORITHM", "RS256")]
    try:
        return jwt.decode(token, key, algorithms=algorithms, issuer=issuer)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc


async def _verify_via_http(token: str) -> Optional[Dict[str, Any]]:
    url = (os.environ.get("BLOCK_A_TOKEN_VALIDATE_URL") or "").strip()
    if not url:
        return None
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            url,
            json={"token": token},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=401,
                detail=f"Block A validate rejected token ({resp.status_code})",
            )
        data = resp.json()
        if isinstance(data, dict) and "tenant_id" in data:
            return data
        if isinstance(data, dict) and "payload" in data:
            return data["payload"]
        raise HTTPException(status_code=401, detail="Block A validate returned unexpected body")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = credentials.credentials
    http_payload = await _verify_via_http(token)
    if http_payload is not None:
        return http_payload
    return _verify_with_block_a_key(token)


async def get_tenant(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing tenant_id claim")
    return str(tenant_id)


def require_scope(required_scope: str):
    async def scope_checker(current_user: Dict[str, Any] = Depends(get_current_user)):
        scopes = current_user.get("scopes", [])
        if required_scope not in scopes and f"scope:{required_scope}" not in scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required scope: {required_scope}",
            )
        return current_user

    return scope_checker
