"""Seed Block K Phase 2 deps: Postgres schema + MinIO objects + ACL grants."""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx
from minio import Minio

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"

DB_URL = os.environ.get("DB_URL", "postgresql://user:pass@localhost:15434/block_d")
STORAGE_ENDPOINT = os.environ.get("STORAGE_ENDPOINT", "localhost:19000")
STORAGE_ACCESS_KEY = os.environ.get("STORAGE_ACCESS_KEY", "minioadmin")
STORAGE_SECRET_KEY = os.environ.get("STORAGE_SECRET_KEY", "minioadmin")
STORAGE_BUCKET = os.environ.get("STORAGE_BUCKET", "documents")
ACL_SERVICE_URL = os.environ.get("ACL_SERVICE_URL", "http://localhost:18001").rstrip("/")

TENANT = "tenant-k"
USER_A = "user-a"
USER_B = "user-b"
LARGE_SIZE = 10 * 1024 * 1024 + 64 * 1024

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    tenant_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    title TEXT,
    object_key TEXT NOT NULL,
    body_size BIGINT NOT NULL DEFAULT 0,
    owner_principal_id TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    visibility_mode TEXT DEFAULT 'acl',
    hidden_fields JSONB DEFAULT '[]'::jsonb,
    acl_entries JSONB DEFAULT '[]'::jsonb,
    structured_metadata JSONB DEFAULT '{}'::jsonb,
    PRIMARY KEY (tenant_id, document_id)
);
"""


def _minio() -> Minio:
    return Minio(
        STORAGE_ENDPOINT.replace("https://", "").replace("http://", ""),
        access_key=STORAGE_ACCESS_KEY,
        secret_key=STORAGE_SECRET_KEY,
        secure=False,
    )


def _put_object(client: Minio, key: str, data: bytes) -> None:
    client.put_object(
        STORAGE_BUCKET,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type="application/octet-stream",
    )


async def _acl(action: str, tenant_id: str, doc_id: str, principal_id: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{ACL_SERVICE_URL}/acl/{action}",
            json={
                "tenant_id": tenant_id,
                "document_id": doc_id,
                "principal_id": principal_id,
            },
        )
        resp.raise_for_status()


async def seed() -> dict:
    dsn = DB_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    await conn.execute(SCHEMA_SQL)

    client = _minio()
    if not client.bucket_exists(STORAGE_BUCKET):
        client.make_bucket(STORAGE_BUCKET)
        print(f"created bucket {STORAGE_BUCKET}")

    structured = json.loads((FIXTURES / "structured_document.json").read_text(encoding="utf-8"))

    docs = []

    # K1 ACL doc
    k1_body = b"Secret body visible only while allowed."
    k1_key = f"{TENANT}/doc-acl-k1.bin"
    _put_object(client, k1_key, k1_body)
    docs.append(
        {
            "document_id": "doc-acl-k1",
            "title": "ACL Recheck Doc",
            "object_key": k1_key,
            "body_size": len(k1_body),
            "owner_principal_id": USER_A,
            "structured_metadata": {},
            "hidden_fields": [],
            "acl_entries": [USER_A],
            "visibility_mode": "acl",
        }
    )

    # K2 large doc
    k2_body = (b"A" * 1024) * (LARGE_SIZE // 1024)
    k2_key = f"{TENANT}/doc-large-k2.bin"
    _put_object(client, k2_key, k2_body)
    docs.append(
        {
            "document_id": "doc-large-k2",
            "title": "Large Streaming Doc",
            "object_key": k2_key,
            "body_size": len(k2_body),
            "owner_principal_id": USER_A,
            "structured_metadata": {
                "headings": ["Huge"],
                "tables": [],
                "code_blocks": [],
                "language": "en",
            },
            "hidden_fields": [],
            "acl_entries": [USER_A],
            "visibility_mode": "acl",
        }
    )

    # K3 structure doc
    k3_body = structured["body"].encode("utf-8")
    k3_key = f"{TENANT}/{structured['document_id']}.bin"
    _put_object(client, k3_key, k3_body)
    docs.append(
        {
            "document_id": structured["document_id"],
            "title": structured["title"],
            "object_key": k3_key,
            "body_size": len(k3_body),
            "owner_principal_id": structured["owner_principal_id"],
            "structured_metadata": structured["structured_metadata"],
            "hidden_fields": structured.get("hidden_fields", []),
            "acl_entries": [structured["owner_principal_id"]],
            "visibility_mode": structured.get("visibility_mode", "acl"),
            "created_at": structured.get("created_at"),
            "updated_at": structured.get("updated_at"),
        }
    )

    # Small control doc
    small = b"hello world"
    small_key = f"{TENANT}/doc-small.bin"
    _put_object(client, small_key, small)
    docs.append(
        {
            "document_id": "doc-small",
            "title": "Small",
            "object_key": small_key,
            "body_size": len(small),
            "owner_principal_id": USER_A,
            "structured_metadata": {},
            "hidden_fields": [],
            "acl_entries": [USER_A],
            "visibility_mode": "acl",
        }
    )

    now = datetime.now(timezone.utc)
    for d in docs:
        created = d.get("created_at")
        updated = d.get("updated_at")
        created_ts = datetime.fromisoformat(created.replace("Z", "+00:00")) if created else now
        updated_ts = datetime.fromisoformat(updated.replace("Z", "+00:00")) if updated else now
        await conn.execute(
            """
            INSERT INTO documents (
                tenant_id, document_id, title, object_key, body_size,
                owner_principal_id, created_at, updated_at, visibility_mode,
                hidden_fields, acl_entries, structured_metadata
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12::jsonb)
            ON CONFLICT (tenant_id, document_id) DO UPDATE SET
                title = EXCLUDED.title,
                object_key = EXCLUDED.object_key,
                body_size = EXCLUDED.body_size,
                owner_principal_id = EXCLUDED.owner_principal_id,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at,
                visibility_mode = EXCLUDED.visibility_mode,
                hidden_fields = EXCLUDED.hidden_fields,
                acl_entries = EXCLUDED.acl_entries,
                structured_metadata = EXCLUDED.structured_metadata
            """,
            TENANT,
            d["document_id"],
            d["title"],
            d["object_key"],
            d["body_size"],
            d["owner_principal_id"],
            created_ts,
            updated_ts,
            d["visibility_mode"],
            json.dumps(d["hidden_fields"]),
            json.dumps(d["acl_entries"]),
            json.dumps(d["structured_metadata"]),
        )
        await _acl("grant", TENANT, d["document_id"], USER_A)
        print(f"seeded {d['document_id']} size={d['body_size']}")

    # Explicitly ensure B has no grant on K1
    await _acl("revoke", TENANT, "doc-acl-k1", USER_B)

    count = await conn.fetchval("SELECT COUNT(*) FROM documents WHERE tenant_id=$1", TENANT)
    await conn.close()
    summary = {
        "tenant": TENANT,
        "documents": count,
        "bucket": STORAGE_BUCKET,
        "acl_url": ACL_SERVICE_URL,
        "db_url": dsn,
        "storage_endpoint": STORAGE_ENDPOINT,
        "large_doc_bytes": LARGE_SIZE,
    }
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    try:
        asyncio.run(seed())
    except Exception as exc:  # noqa: BLE001
        print(f"SEED FAILED: {exc}", file=sys.stderr)
        raise