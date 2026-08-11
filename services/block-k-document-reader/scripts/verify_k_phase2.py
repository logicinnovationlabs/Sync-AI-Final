"""Block K Phase 2 verification against Postgres + MinIO + ACL mock."""

from __future__ import annotations

import base64
import json
import os
import sys
import tracemalloc
from pathlib import Path

# Force Phase 2 backends before app imports
os.environ["ENVIRONMENT"] = "test"
os.environ["STORAGE_BACKEND"] = "minio"
os.environ["ACL_BACKEND"] = "http"
os.environ.setdefault("STORAGE_ENDPOINT", "localhost:19000")
os.environ.setdefault("STORAGE_ACCESS_KEY", "minioadmin")
os.environ.setdefault("STORAGE_SECRET_KEY", "minioadmin")
os.environ.setdefault("STORAGE_BUCKET", "documents")
os.environ.setdefault("DB_URL", "postgresql://user:pass@localhost:15434/block_d")
os.environ.setdefault("ACL_SERVICE_URL", "http://localhost:18001")
os.environ.setdefault("STREAM_THRESHOLD_BYTES", str(10 * 1024 * 1024))
os.environ.setdefault("ENFORCE_TENANT_ISOLATION", "true")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from httpx import ASGITransport

TENANT = "tenant-k"
USER_A = "user-a"
USER_B = "user-b"
RESULTS: list[dict] = []


def make_bearer(tenant_id: str, principal_id: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "principal_id": principal_id,
                "scopes": ["document.read"],
            }
        ).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.testsig"


def record(criterion: str, passed: bool, detail: str) -> None:
    RESULTS.append({"id": criterion, "pass": passed, "detail": detail})
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {criterion}: {detail}")


async def acl_post(action: str, doc_id: str, principal_id: str) -> None:
    url = os.environ["ACL_SERVICE_URL"].rstrip("/") + f"/acl/{action}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            url,
            json={
                "tenant_id": TENANT,
                "document_id": doc_id,
                "principal_id": principal_id,
            },
        )
        resp.raise_for_status()


async def run() -> int:
    # Import after env is set so Settings picks up Phase 2 values
    from app.config import Settings
    from app.storage.document_store import create_document_store
    from app.acl.acl_checker import create_acl_checker
    import app.main as main_mod

    settings = Settings()
    assert settings.storage_backend == "minio", settings.storage_backend
    assert settings.acl_backend == "http", settings.acl_backend

    store = create_document_store(settings)
    acl = create_acl_checker(settings)
    await store.connect()
    main_mod.store = store
    main_mod.acl_checker = acl

    transport = ASGITransport(app=main_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://phase2") as client:
        # ---- K1 ----
        await acl_post("grant", "doc-acl-k1", USER_A)
        resp_a = await client.get(
            "/api/v1/document/doc-acl-k1",
            headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
        )
        ok_a = resp_a.status_code == 200 and "Secret body" in resp_a.json().get("body", "")
        resp_b = await client.get(
            "/api/v1/document/doc-acl-k1",
            headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_B)}"},
        )
        ok_b = resp_b.status_code == 403

        await acl_post("revoke", "doc-acl-k1", USER_A)
        denied = 0
        for _ in range(10):
            r = await client.get(
                "/api/v1/document/doc-acl-k1",
                headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
            )
            if r.status_code == 403:
                denied += 1
        # restore grant for later tests that may share ACL mock state
        await acl_post("grant", "doc-acl-k1", USER_A)

        k1_pass = ok_a and ok_b and denied == 10
        record(
            "K1",
            k1_pass,
            f"allow={resp_a.status_code} deny_b={resp_b.status_code} post_revoke_403={denied}/10",
        )

        # ---- K2 ----
        resp = await client.get(
            "/api/v1/document/doc-large-k2",
            headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
        )
        streaming = resp.headers.get("x-document-streaming") == "1"
        body_len = 0
        if resp.status_code == 200:
            body_len = len(resp.json().get("body", ""))

        # Generator memory bound (MinIO stream)
        from app.services.document_reader import stream_document_json

        meta = await store.get_metadata(TENANT, "doc-large-k2")
        structured = await store.get_structured_metadata(TENANT, "doc-large-k2")
        tracemalloc.start()
        baseline = tracemalloc.get_traced_memory()[0]
        total = 0
        peak_seen = 0
        async for chunk in stream_document_json(
            store,
            meta["object_key"],
            "doc-large-k2",
            TENANT,
            meta,
            structured,
        ):
            total += len(chunk)
            _cur, peak = tracemalloc.get_traced_memory()
            peak_seen = max(peak_seen, peak)
        growth = peak_seen - baseline
        tracemalloc.stop()

        k2_pass = (
            resp.status_code == 200
            and streaming
            and body_len > 10 * 1024 * 1024
            and growth < 5 * 1024 * 1024
        )
        record(
            "K2",
            k2_pass,
            f"status={resp.status_code} streaming={streaming} body_len={body_len} gen_growth={growth}",
        )

        # ---- K3 ----
        fixture = json.loads((ROOT / "fixtures" / "structured_document.json").read_text(encoding="utf-8"))
        resp3 = await client.get(
            f"/api/v1/document/{fixture['document_id']}",
            headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
        )
        data = resp3.json() if resp3.status_code == 200 else {}
        struct_ok = data.get("structured_metadata") == fixture["structured_metadata"]
        body_ok = data.get("body") == fixture["body"]
        title_ok = data.get("title") == fixture["title"]
        k3_pass = resp3.status_code == 200 and struct_ok and body_ok and title_ok
        record(
            "K3",
            k3_pass,
            f"status={resp3.status_code} structure_match={struct_ok} body_match={body_ok} title_match={title_ok}",
        )

        # small doc sanity (not streamed)
        small = await client.get(
            "/api/v1/document/doc-small",
            headers={"Authorization": f"Bearer {make_bearer(TENANT, USER_A)}"},
        )
        record(
            "K2-small",
            small.status_code == 200 and small.headers.get("x-document-streaming") is None,
            f"status={small.status_code} streaming_header={small.headers.get('x-document-streaming')}",
        )

    await store.close()

    evidence = {
        "phase": 2,
        "backends": {
            "storage": settings.storage_backend,
            "acl": settings.acl_backend,
            "db_url": settings.db_url,
            "storage_endpoint": settings.storage_endpoint,
            "acl_service_url": settings.acl_service_url,
        },
        "results": RESULTS,
        "overall": all(r["pass"] for r in RESULTS if r["id"] in {"K1", "K2", "K3"}),
    }
    out = ROOT / "evidence" / "k_phase2_20260811.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"\nEvidence: {out}")
    print(f"OVERALL: {'PASS' if evidence['overall'] else 'FAIL'}")
    return 0 if evidence["overall"] else 1


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(run()))