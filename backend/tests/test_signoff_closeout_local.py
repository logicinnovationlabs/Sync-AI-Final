"""
Block A closeout signoff tests A1–A5 against real Postgres (block-a-verify-pg:5434) + Redis.

These replace simulated assertions in test_signoff.py for genuine PASS evidence:
- A1: 100 tokens, per-token evidence, mixed interactive + service
- A2: 20 trials, revoke then poll GET /api/v1/me every 5s
- A3: SCIM sync via 3 separate OS processes (genuine restart)
- A4: 50 HTTP attempts of tenant-A token against tenant-B-scoped endpoints
- A5: every scoped route from the route table, missing scope → 403 ErrorResponse
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Force no .env before app imports (conftest may already import app — set in pytest.ini / cmdline too)
os.environ.setdefault("SNYQ_IGNORE_ENV_FILE", "1")

from app.main import app
from app.services.token_service import token_service
from app.storage.redis_client import redis_client

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCIM_SCRIPT = BACKEND_ROOT / "scripts" / "scim_sync_once.py"
SCIM_FIXTURE = BACKEND_ROOT / "fixtures" / "okta_scim_users.json"
DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:verify@localhost:5434/block_a_verify",
)


def _scoped_routes_from_app():
    """Enumerate every route that depends on require_scope (A5 must cover all)."""
    routes = []
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        # Walk dependencies for require_scope closures by required scope name in qualname/repr
        stack = list(getattr(dependant, "dependencies", []) or [])
        required = set()
        while stack:
            dep = stack.pop()
            call = getattr(dep, "call", None)
            if call is not None:
                name = getattr(call, "__name__", "")
                # scope_checker is nested inside require_scope(required_scope)
                if name == "scope_checker":
                    # recover required scope from closure cells
                    for cell in (call.__closure__ or ()):
                        try:
                            val = cell.cell_contents
                        except ValueError:
                            continue
                        if isinstance(val, str) and "." in val:
                            required.add(val)
            stack.extend(getattr(dep, "dependencies", []) or [])
        if required and hasattr(route, "path") and hasattr(route, "methods"):
            for method in (route.methods or set()) - {"HEAD", "OPTIONS"}:
                for scope in required:
                    routes.append({"method": method, "path": route.path, "scope": scope})
    return routes


@pytest.mark.asyncio
async def test_A1_tenant_binding_integrity_closeout():
    """A1: 100 tokens across 3 tenants, mixed interactive + service; paste per-token data."""
    tenants = [str(uuid4()), str(uuid4()), str(uuid4())]
    results = []

    for i in range(100):
        tenant_id = tenants[i % 3]
        principal_id = str(uuid4())
        # Mixed interactive (user scopes) + service (client_credentials-like scopes)
        if i % 2 == 0:
            scopes = ["search.read", "document.read"]
            token_kind = "interactive"
        else:
            scopes = ["connectors.write", "connectors.read"]
            token_kind = "service"

        token = await token_service.issue_access_token(tenant_id, principal_id, scopes)
        header = jwt.get_unverified_header(token)
        payload = await token_service.validate_token(token)

        tenant_keys = [k for k in payload.keys() if k == "tenant_id"]
        ok = (
            len(tenant_keys) == 1
            and payload.get("tenant_id") == tenant_id
            and payload.get("exp") is not None
            and header.get("kid") is not None
        )
        results.append(
            {
                "n": i + 1,
                "kind": token_kind,
                "tenant_id": payload.get("tenant_id"),
                "tenant_id_keys": len(tenant_keys),
                "kid": header.get("kid"),
                "sub": payload.get("sub"),
                "ok": ok,
            }
        )
        print(
            f"A1 token {i+1:03d} kind={token_kind} tenant_id={payload.get('tenant_id')} "
            f"kid={header.get('kid')} keys={len(tenant_keys)} ok={ok}"
        )

    failed = [r for r in results if not r["ok"]]
    assert not failed, f"A1 FAILED: {len(failed)} tokens failed"
    print(f"A1 PASSED: 100/100 tokens contain exactly one tenant_id and pass validation")


@pytest.mark.asyncio
async def test_A2_revocation_latency_closeout():
    """A2: 20 trials — revoke, poll GET /api/v1/me every 5s until 401, latency ≤60s."""
    transport = ASGITransport(app=app)
    trial_results = []

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for trial in range(1, 21):
            tenant_id = str(uuid4())
            principal_id = str(uuid4())
            token = await token_service.issue_access_token(
                tenant_id, principal_id, ["search.read"]
            )
            headers = {"Authorization": f"Bearer {token}"}

            # Confirm protected endpoint accepts pre-revoke
            pre = await client.get("/api/v1/me", headers=headers)
            assert pre.status_code == 200, f"Trial {trial}: pre-revoke /me expected 200 got {pre.status_code}"

            payload = await token_service.decode_without_validation(token)
            jti = payload["jti"]

            # Revoke (session/token) via Redis set checked by validate_token
            await redis_client.sadd(tenant_id, f"revoked:{jti}", jti)
            revoked_at = time.time()

            rejected_at = None
            poll_statuses = []
            # Poll every 5s for up to 60s (include immediate first poll at t≈0)
            for poll in range(0, 13):
                if poll > 0:
                    await asyncio.sleep(5)
                resp = await client.get("/api/v1/me", headers=headers)
                poll_statuses.append(resp.status_code)
                if resp.status_code in (401, 403):
                    rejected_at = time.time()
                    break

            latency = (rejected_at - revoked_at) if rejected_at else None
            ok = rejected_at is not None and latency <= 60.0
            trial_results.append(
                {
                    "trial": trial,
                    "latency_s": latency,
                    "poll_statuses": poll_statuses,
                    "ok": ok,
                }
            )
            print(
                f"A2 trial {trial:02d} latency={latency} statuses={poll_statuses} ok={ok}"
            )
            assert ok, f"A2 trial {trial} failed: latency={latency} statuses={poll_statuses}"

    assert all(t["ok"] for t in trial_results)
    print("A2 PASSED: 20/20 trials rejected within <=60s")


def test_A3_scim_idempotency_process_restart_closeout():
    """A3: sync 3× via separate OS processes against unchanged Okta-shaped fixture."""
    tenant_id = str(uuid4())
    runs = []
    pids = set()

    # Shared verify DB may retain users from prior runs (idp_subject is globally unique).
    # Clear only the Okta fixture subjects once, then prove idempotent recreate across process restarts.
    import asyncio
    from sqlalchemy import delete, text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.models.user import User
    from app.models.base import Base

    fixture_users = json.loads(SCIM_FIXTURE.read_text(encoding="utf-8"))
    subjects = [u["id"] for u in fixture_users]

    async def _cleanup():
        engine = create_async_engine(DB_URL, echo=False, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(delete(User).where(User.idp_subject.in_(subjects)))
        await engine.dispose()

    asyncio.run(_cleanup())

    for run in range(1, 4):
        proc = subprocess.run(
            [
                sys.executable,
                str(SCIM_SCRIPT),
                "--tenant-id",
                tenant_id,
                "--fixture",
                str(SCIM_FIXTURE),
                "--database-url",
                DB_URL,
            ],
            cwd=str(BACKEND_ROOT),
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "SNYQ_IGNORE_ENV_FILE": "1",
                "TEST_DATABASE_URL": DB_URL,
                "CONTROL_PLANE_DATABASE_URL": DB_URL,
            },
            check=False,
        )
        print(f"A3 run {run} exit={proc.returncode} stderr={proc.stderr[-500:]}")
        assert proc.returncode == 0, f"A3 run {run} failed: {proc.stderr}"
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        runs.append(data["principals"])
        pids.add(data["pid"])
        print(f"A3 run {run} pid={data['pid']} principals={data['principals']}")

    assert len(pids) == 3, f"A3 FAILED: expected 3 distinct PIDs (true restarts), got {pids}"
    assert runs[0] == runs[1] == runs[2], f"A3 FAILED: drift across runs: {runs}"
    assert len(runs[0]) >= 3, f"A3 FAILED: expected >=3 users from Okta fixture, got {runs[0]}"
    print(f"A3 PASSED: principal_id identical across 3 process restarts, 0 drift; pids={pids}")


@pytest.mark.asyncio
async def test_A4_cross_tenant_replay_rejection_closeout():
    """A4: 50 HTTP attempts — tenant-A token to tenant-B-scoped endpoints → 401/403."""
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    token_a = await token_service.issue_access_token(
        tenant_a, str(uuid4()), ["search.read", "document.read", "admin.audit.read"]
    )

    endpoints = [
        "/api/v1/scoped/search",
        "/api/v1/scoped/documents",
        "/api/v1/scoped/admin/audit",
    ]

    transport = ASGITransport(app=app)
    results = []
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for attempt in range(1, 51):
            path = endpoints[(attempt - 1) % len(endpoints)]
            resp = await client.get(
                path,
                headers={
                    "Authorization": f"Bearer {token_a}",
                    "X-Tenant-ID": tenant_b,  # B-scoped request with A token
                },
            )
            rejected = resp.status_code in (401, 403)
            leaked = resp.status_code == 200
            results.append(
                {
                    "attempt": attempt,
                    "path": path,
                    "status": resp.status_code,
                    "rejected": rejected,
                    "leaked": leaked,
                }
            )
            print(f"A4 attempt {attempt:02d} {path} status={resp.status_code} rejected={rejected}")
            assert rejected and not leaked, f"A4 attempt {attempt} leaked or not rejected: {resp.status_code} {resp.text}"

    assert len(results) == 50
    assert all(r["rejected"] for r in results)
    assert not any(r["leaked"] for r in results)
    print("A4 PASSED: 50/50 cross-tenant replay attempts rejected, 0 leaks")


@pytest.mark.asyncio
async def test_A5_scope_enforcement_closeout():
    """A5: every scoped endpoint from route table returns 403 ErrorResponse without scope."""
    scoped = _scoped_routes_from_app()
    assert scoped, "A5 FAILED: no scoped routes discovered on app"
    print(f"A5 discovered scoped routes ({len(scoped)}):")
    for r in scoped:
        print(f"  {r['method']} {r['path']} requires {r['scope']}")

    tenant_id = str(uuid4())
    # Token missing all relevant scopes
    token = await token_service.issue_access_token(tenant_id, str(uuid4()), ["other.scope"])
    transport = ASGITransport(app=app)
    results = []

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for r in scoped:
            # Skip connector routes that need path params we can't invent safely without side effects
            path = r["path"]
            if "{" in path:
                # Fill path params with placeholders for enforcement check
                path = (
                    path.replace("{source_type}", "google_drive")
                )
            method = r["method"].lower()
            headers = {
                "Authorization": f"Bearer {token}",
                "X-Tenant-ID": tenant_id,
            }
            if method == "get":
                resp = await client.get(path, headers=headers)
            elif method == "post":
                resp = await client.post(path, headers=headers, json={})
            else:
                resp = await client.request(method.upper(), path, headers=headers)

            body = {}
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}

            envelope_ok = (
                isinstance(body, dict)
                and "error" in body
                and isinstance(body["error"], dict)
                and "code" in body["error"]
                and "message" in body["error"]
            )
            ok = resp.status_code == 403 and envelope_ok
            results.append(
                {
                    "method": r["method"],
                    "path": path,
                    "scope": r["scope"],
                    "status": resp.status_code,
                    "envelope_ok": envelope_ok,
                    "body": body,
                    "ok": ok,
                }
            )
            print(
                f"A5 {r['method']} {path} scope={r['scope']} status={resp.status_code} "
                f"envelope={envelope_ok} ok={ok}"
            )

    failed = [x for x in results if not x["ok"]]
    assert not failed, f"A5 FAILED: {failed}"
    print(f"A5 PASSED: {len(results)}/{len(results)} scoped endpoints returned 403 error envelope")
