"""
Backup and Restore utilities for Block D.

Per-tenant schema dumps are stored in-process for tests and optionally uploaded
to the configured backup bucket (MinIO/S3) when BACKUP_BUCKET is set.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)

_backup_metadata_store: Dict[str, "BackupMetadata"] = {}
_backup_data_store: Dict[str, str] = {}
_BACKUP_DIR = Path(settings.backup_local_dir)


class BackupMetadata:
    """Metadata for a backup operation."""

    __slots__ = (
        "backup_id",
        "tenant_id",
        "schema_name",
        "timestamp",
        "row_count",
        "checksum",
        "size_bytes",
    )

    def __init__(
        self,
        backup_id: str,
        tenant_id: str,
        schema_name: str,
        timestamp: datetime,
        row_count: int,
        checksum: str,
        size_bytes: int,
    ):
        self.backup_id = backup_id
        self.tenant_id = tenant_id
        self.schema_name = schema_name
        self.timestamp = timestamp
        self.row_count = row_count
        self.checksum = checksum
        self.size_bytes = size_bytes


def _schema_name(tenant_id: str) -> str:
    return f"tenant_{tenant_id.replace('-', '_')}"


async def _dump_schema(session_factory, schema_name: str) -> tuple[str, int]:
    """Dump documents table rows from a tenant schema as JSON."""
    async with session_factory() as session:
        exists = await session.execute(
            text(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"
            ),
            {"schema": schema_name},
        )
        if exists.scalar_one_or_none() is None:
            payload = json.dumps({"schema": schema_name, "tables": {}})
            return payload, 0

        tables: Dict[str, Any] = {}
        row_count = 0
        table_exists = await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = :schema AND table_name = 'documents'
                """
            ),
            {"schema": schema_name},
        )
        if table_exists.scalar_one_or_none() is not None:
            result = await session.execute(
                text(f'SELECT id, content FROM "{schema_name}".documents ORDER BY id')
            )
            rows = [{"id": r[0], "content": r[1]} for r in result.fetchall()]
            tables["documents"] = rows
            row_count = len(rows)

        payload = json.dumps({"schema": schema_name, "tables": tables}, sort_keys=True)
        return payload, row_count


async def _restore_schema(session_factory, schema_name: str, payload: str) -> int:
    data = json.loads(payload)
    tables = data.get("tables") or {}
    documents = tables.get("documents") or []

    async with session_factory() as session:
        await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        await session.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS "{schema_name}".documents (
                    id SERIAL PRIMARY KEY,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
        )
        await session.execute(text(f'TRUNCATE "{schema_name}".documents'))
        for row in documents:
            await session.execute(
                text(f'INSERT INTO "{schema_name}".documents (id, content) VALUES (:id, :content)'),
                {"id": row["id"], "content": row["content"]},
            )
        await session.commit()
    return len(documents)


def _persist_artifact(backup_id: str, payload: str) -> None:
    _backup_data_store[backup_id] = payload
    try:
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        (_BACKUP_DIR / f"{backup_id}.json").write_text(payload, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write local backup file: %s", exc)

    bucket = getattr(settings, "backup_bucket", None)
    if bucket:
        try:
            from app.storage.object_store import ObjectStorageClient
            from app.storage.vault_client import vault_client

            store = ObjectStorageClient(
                storage_client=None,
                vault_client=vault_client,
                bucket_name=bucket,
            )
            store.upload(
                tenant_id="platform",
                connector_instance_id="backups",
                object_path=f"{backup_id}.json",
                data=payload.encode("utf-8"),
            )
        except Exception as exc:
            logger.warning("Backup upload to object store failed: %s", exc)


def _load_artifact(backup_id: str) -> str:
    if backup_id in _backup_data_store:
        return _backup_data_store[backup_id]
    path = _BACKUP_DIR / f"{backup_id}.json"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    raise ValueError(f"Backup {backup_id} not found")


async def backup_tenant(db_client, tenant_id: str) -> BackupMetadata:
    """Dump tenant schema data and record checksum metadata."""
    schema_name = _schema_name(tenant_id)
    backup_id = f"backup_{tenant_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"

    logger.info("Starting backup for tenant %s (schema: %s)", tenant_id, schema_name)
    payload, row_count = await _dump_schema(db_client, schema_name)
    checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    metadata = BackupMetadata(
        backup_id=backup_id,
        tenant_id=tenant_id,
        schema_name=schema_name,
        timestamp=datetime.now(timezone.utc),
        row_count=row_count,
        checksum=checksum,
        size_bytes=len(payload.encode("utf-8")),
    )
    _backup_metadata_store[backup_id] = metadata
    _persist_artifact(backup_id, payload)
    logger.info("Backup complete: %s (%s rows)", backup_id, row_count)
    return metadata


async def restore_tenant(db_client, tenant_id: str, backup_id: str) -> BackupMetadata:
    """Restore tenant schema from a prior backup."""
    if backup_id not in _backup_metadata_store:
        raise ValueError(f"Backup {backup_id} not found")

    metadata = _backup_metadata_store[backup_id]
    payload = _load_artifact(backup_id)
    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != metadata.checksum:
        raise ValueError(f"Backup {backup_id} checksum mismatch")

    logger.info("Restoring tenant %s from backup %s", tenant_id, backup_id)
    row_count = await _restore_schema(db_client, metadata.schema_name, payload)
    restored = BackupMetadata(
        backup_id=backup_id,
        tenant_id=tenant_id,
        schema_name=metadata.schema_name,
        timestamp=datetime.now(timezone.utc),
        row_count=row_count,
        checksum=metadata.checksum,
        size_bytes=metadata.size_bytes,
    )
    return restored


def drop_tenant(db_client, tenant_id: str) -> None:
    """Drop a tenant schema."""
    import asyncio

    schema_name = _schema_name(tenant_id)
    logger.info("Dropping tenant %s (schema: %s)", tenant_id, schema_name)

    async def _drop() -> None:
        async with db_client() as session:
            await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
            await session.commit()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_drop())
    else:
        if loop.is_running():
            import nest_asyncio

            nest_asyncio.apply()
            loop.run_until_complete(_drop())
        else:
            asyncio.run(_drop())

    logger.info("Tenant %s dropped successfully", tenant_id)
