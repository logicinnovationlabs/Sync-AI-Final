"""Document store — Block D object storage + relational metadata."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional, Protocol

import asyncpg

from app.config import Settings

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

    def upsert(
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
        dsn = self.settings.db_url.replace("postgresql+asyncpg://", "postgresql://")
        self.db_pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        logger.info("Connected to Block D Postgres for document metadata")

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
                       structured_metadata
                FROM documents
                WHERE tenant_id = $1 AND document_id = $2
                """,
                tenant_id,
                doc_id,
            )
            if not row:
                return None
            data = dict(row)
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
