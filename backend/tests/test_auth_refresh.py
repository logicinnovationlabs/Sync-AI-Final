"""Native /auth/refresh — access JWT is 1h; SPA must be able to mint a new one."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_rotate_refresh_token_rejects_replay():
    from app.services.token_service import token_service

    tenant_id, principal_id = str(uuid4()), str(uuid4())
    refresh_1 = await token_service.issue_refresh_token(tenant_id, principal_id)
    access, refresh_2 = await token_service.rotate_refresh_token(refresh_1)
    assert access
    assert refresh_2 != refresh_1
    with pytest.raises(Exception):
        await token_service.rotate_refresh_token(refresh_1)


@pytest.mark.asyncio
async def test_refresh_endpoint_rejects_garbage_and_access_jwt():
    from app.main import app
    from app.services.token_service import token_service

    client = TestClient(app)
    bad = client.post("/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert bad.status_code == 401

    access = await token_service.issue_access_token(
        tenant_id=str(uuid4()),
        principal_id=str(uuid4()),
        scopes=["connectors.read"],
    )
    wrong_type = client.post("/auth/refresh", json={"refresh_token": access})
    assert wrong_type.status_code == 401
