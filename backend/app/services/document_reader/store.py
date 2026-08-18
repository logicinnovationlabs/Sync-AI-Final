"""Document store — Block D object storage + relational metadata."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional, Protocol

import asyncpg

from app.core.config import Settings

logger = logging.getLogger(__name__)


class DocumentStore(Protocol):
    """Interface for document metadata + body retrieval."""

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def get_metadata(
        self, tenant_id: str, doc_id: str
    ) -> Optional[Dict[str, Any]]: ...

    async def get_body(self, object_key: str) -> bytes: ...

    def get_body_stream(self, object_key: str) -> AsyncGenerator[bytes, None]: ...

    async def get_structured_metadata(
        self, tenant_id: str, doc_id: str
    ) -> Optional[Dict[str, Any]]: ...


class InMemoryDocumentStore:
    """Phase 1 mock store — tenant-isolated in-memory documents."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings
        self._docs: Dict[tuple[str, str], Dict[str, Any]] = {}
        self._objects: Dict[str, bytes] = {}

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def upsert(
        self,
        tenant_id: str,
        document_id: str,
        *,
        title: str = "",
        body: str | bytes = "",
        structured_metadata: Optional[Dict[str, Any]] = None,
        owner_principal_id: str = "",
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        visibility_mode: str = "acl",
        hidden_fields: Optional[list[str]] = None,
        acl_entries: Optional[list[str]] = None,
        object_key: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        key = object_key or f"{tenant_id}/{document_id}.bin"
        meta = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "title": title,
            "object_key": key,
            "body_size": len(body_bytes),
            "owner_principal_id": owner_principal_id,
            "created_at": created_at,
            "updated_at": updated_at,
            "visibility_mode": visibility_mode,
            "hidden_fields": list(hidden_fields or []),
            "acl_entries": list(acl_entries or []),
            "structured_metadata": structured_metadata or {},
        }
        if extra:
            meta.update(extra)
        self._docs[(tenant_id, document_id)] = meta
        self._objects[key] = body_bytes
        return meta

    def delete(self, tenant_id: str, document_id: str) -> None:
        meta = self._docs.pop((tenant_id, document_id), None)
        if meta:
            self._objects.pop(meta.get("object_key", ""), None)

    async def get_metadata(
        self, tenant_id: str, doc_id: str
    ) -> Optional[Dict[str, Any]]:
        meta = self._docs.get((tenant_id, doc_id))
        return dict(meta) if meta else None

    async def get_body(self, object_key: str) -> bytes:
        if object_key not in self._objects:
            raise FileNotFoundError(f"Object not found: {object_key}")
        return self._objects[object_key]

    async def get_body_stream(self, object_key: str) -> AsyncGenerator[bytes, None]:
        data = await self.get_body(object_key)
        chunk = 8192
        if self.settings:
            chunk = self.settings.stream_chunk_bytes
        for i in range(0, len(data), chunk):
            yield data[i : i + chunk]
            await asyncio.sleep(0)

    async def get_structured_metadata(
        self, tenant_id: str, doc_id: str
    ) -> Optional[Dict[str, Any]]:
        meta = await self.get_metadata(tenant_id, doc_id)
        if not meta:
            return None
        return dict(meta.get("structured_metadata") or {})


class MinioDocumentStore:
    """Phase 2 store — Postgres metadata + MinIO object bodies (Block D)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_pool: Optional[asyncpg.Pool] = None
        endpoint = settings.storage_endpoint.replace("https://", "").replace("http://", "")
        from minio import Minio

        self.minio = Minio(
            endpoint,
            access_key=settings.storage_access_key,
            secret_key=settings.storage_secret_key,
            secure=settings.storage_secure,
        )

    async def connect(self) -> None:
        dsn = self.settings.control_plane_database_url.replace("postgresql+asyncpg://", "postgresql://")
        self.db_pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        await self.ensure_schema()
        await asyncio.to_thread(self.ensure_bucket)
        logger.info("Connected to Block D Postgres for document metadata")

    async def ensure_schema(self) -> None:
        """Create the K document-metadata table if Block D Postgres does not have it."""
        if not self.db_pool:
            raise RuntimeError("DocumentStore not connected")
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    tenant_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    object_key TEXT NOT NULL,
                    body_size BIGINT NOT NULL DEFAULT 0,
                    owner_principal_id TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ,
                    visibility_mode TEXT NOT NULL DEFAULT 'acl',
                    hidden_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
                    acl_entries JSONB NOT NULL DEFAULT '[]'::jsonb,
                    structured_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    extra JSONB NOT NULL DEFAULT '{}'::jsonb,
                    PRIMARY KEY (tenant_id, document_id)
                )
                """
            )

    def ensure_bucket(self) -> None:
        bucket = self.settings.storage_bucket
        if not self.minio.bucket_exists(bucket):
            self.minio.make_bucket(bucket)

    async def upsert(
        self,
        tenant_id: str,
        document_id: str,
        *,
        title: str = "",
        body: str | bytes = "",
        structured_metadata: Optional[Dict[str, Any]] = None,
        owner_principal_id: str = "",
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        visibility_mode: str = "acl",
        hidden_fields: Optional[list[str]] = None,
        acl_entries: Optional[list[str]] = None,
        object_key: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Write metadata to Postgres and the body to MinIO (Phase 2 seed/read path)."""
        if not self.db_pool:
            raise RuntimeError("DocumentStore not connected")
        from io import BytesIO

        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        key = object_key or f"{tenant_id}/{document_id}.bin"
        hidden = list(hidden_fields or [])
        acls = list(acl_entries or [])
        structured = structured_metadata or {}
        extra_data = dict(extra or {})

        def _as_dt(value: Any):
            if value is None or value == "":
                return None
            if isinstance(value, datetime):
                return value
            text = str(value).replace("Z", "+00:00")
            return datetime.fromisoformat(text)

        created_dt = _as_dt(created_at)
        updated_dt = _as_dt(updated_at)
        meta = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "title": title,
            "object_key": key,
            "body_size": len(body_bytes),
            "owner_principal_id": owner_principal_id,
            "created_at": created_at,
            "updated_at": updated_at,
            "visibility_mode": visibility_mode,
            "hidden_fields": hidden,
            "acl_entries": acls,
            "structured_metadata": structured,
        }
        meta.update(extra_data)

        def _put() -> None:
            self.ensure_bucket()
            self.minio.put_object(
                self.settings.storage_bucket,
                key,
                BytesIO(body_bytes),
                len(body_bytes),
            )

        await asyncio.to_thread(_put)
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (
                    tenant_id, document_id, title, object_key, body_size,
                    owner_principal_id, created_at, updated_at, visibility_mode,
                    hidden_fields, acl_entries, structured_metadata, extra
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9,
                    $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb
                )
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
                    structured_metadata = EXCLUDED.structured_metadata,
                    extra = EXCLUDED.extra
                """,
                tenant_id,
                document_id,
                title,
                key,
                len(body_bytes),
                owner_principal_id,
                created_dt,
                updated_dt,
                visibility_mode,
                json.dumps(hidden),
                json.dumps(acls),
                json.dumps(structured),
                json.dumps(extra_data),
            )
        return meta

    async def close(self) -> None:
        if self.db_pool:
            await self.db_pool.close()
            self.db_pool = None

    async def get_metadata(
        self, tenant_id: str, doc_id: str
    ) -> Optional[Dict[str, Any]]:
        if not self.db_pool:
            raise RuntimeError("DocumentStore not connected")
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT document_id, tenant_id, title, object_key, body_size,
                       owner_principal_id, created_at, updated_at,
                       visibility_mode, hidden_fields, acl_entries,
                       structured_metadata, extra
                FROM documents
                WHERE tenant_id = $1 AND document_id = $2
                """,
                tenant_id,
                doc_id,
            )
            if not row:
                return None
            data = dict(row)
            extra = data.pop("extra", None) or {}
            for key in ("created_at", "updated_at"):
                if data.get(key) is not None:
                    data[key] = data[key].isoformat()
            for key in ("hidden_fields", "acl_entries", "structured_metadata"):
                val = data.get(key)
                if isinstance(val, str):
                    try:
                        data[key] = json.loads(val)
                    except json.JSONDecodeError:
                        pass
            if isinstance(extra, str):
                try:
                    extra = json.loads(extra)
                except json.JSONDecodeError:
                    extra = {}
            if isinstance(extra, dict):
                data.update(extra)
            return data

    async def get_body(self, object_key: str) -> bytes:
        chunks: list[bytes] = []
        async for chunk in self.get_body_stream(object_key):
            chunks.append(chunk)
        return b"".join(chunks)

    async def get_body_stream(self, object_key: str) -> AsyncGenerator[bytes, None]:
        from minio.error import S3Error

        def _open():
            return self.minio.get_object(self.settings.storage_bucket, object_key)

        try:
            response = await asyncio.to_thread(_open)
        except S3Error as exc:
            raise FileNotFoundError(f"Object not found: {object_key}") from exc

        chunk_size = self.settings.stream_chunk_bytes
        try:
            while True:
                chunk = await asyncio.to_thread(response.read, chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            response.close()
            response.release_conn()

    async def get_structured_metadata(
        self, tenant_id: str, doc_id: str
    ) -> Optional[Dict[str, Any]]:
        meta = await self.get_metadata(tenant_id, doc_id)
        if not meta:
            return None
        structured = meta.get("structured_metadata") or {}
        return dict(structured) if isinstance(structured, dict) else {}


def create_document_store(settings: Settings) -> InMemoryDocumentStore | MinioDocumentStore:
    """Factory: mock for Phase 1, MinIO/Postgres for Phase 2."""
    if settings.storage_backend == "minio":
        return MinioDocumentStore(settings)
    return InMemoryDocumentStore(settings)


_SHARED_STORE: Optional[InMemoryDocumentStore | MinioDocumentStore] = None


def get_shared_document_store():
    """Same store instance used by GET /document/{id} and Google backfill."""
    global _SHARED_STORE
    if _SHARED_STORE is None:
        from app.core.config import settings as app_settings

        _SHARED_STORE = create_document_store(app_settings)
    return _SHARED_STORE
