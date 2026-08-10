"""Phase 2 JWT check: reject forged token; accept Block A signed token."""
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(r"D:\PROJECTS\Sync Ai Final\backend")
sys.path.insert(0, str(SERVICE_ROOT))

os.environ.setdefault("JWT_PUBLIC_KEY_PATH", str(BACKEND / "keys" / "public.pem"))
os.environ.setdefault("JWT_ISSUER", "snyq-platform")
os.environ.setdefault("JWT_ALGORITHM", "RS256")

import asyncio
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.auth.jwt_auth import get_current_user
from fastapi.security import HTTPAuthorizationCredentials


async def main():
    # Forged unsigned/HS256 style token must fail
    forged = "eyJhbGciOiJub25lIn0.eyJ0ZW5hbnRfaWQiOiJmYWtlIiwic2NvcGVzIjpbImVtYmVkLndyaXRlIl19."
    try:
        await get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged))
        print("JWT_FORGED_ACCEPTED — FAIL")
        return False
    except HTTPException as e:
        print(f"JWT_FORGED_REJECTED status={e.status_code} — OK")

    priv = (BACKEND / "keys" / "private.pem").read_text(encoding="utf-8")
    now = datetime.now(timezone.utc)
    payload = {
        "tenant_id": "tenant_e_phase2",
        "principal_id": "user_e_test",
        "scopes": ["embed.write", "embed.read"],
        "iss": "snyq-platform",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "jti": "e2-jwt-test",
    }
    token = jwt.encode(payload, priv, algorithm="RS256", headers={"kid": "key-2026-08"})
    user = await get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert user["tenant_id"] == "tenant_e_phase2"
    print(f"JWT_SIGNED_ACCEPTED tenant={user['tenant_id']} — OK")
    return True


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
