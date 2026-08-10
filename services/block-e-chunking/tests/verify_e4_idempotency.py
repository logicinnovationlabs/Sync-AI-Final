"""
E4 Idempotency against real Postgres + current atomic UPDATE write path (v7.0 §4.5).

Reprocesses the same document 3x through: chunking → deterministic chunk_id →
placeholder row insert → real Celery embedding_task (atomic conditional UPDATE).
Also verifies content-change and chunker_version-bump produce different chunk_ids.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.chunkers.code_chunker import CodeChunker
from app.models.chunk_record import ChunkRecord
from app.workers.embedding_worker import embedding_task

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:verify@localhost:5433/block_e_verify",
)
SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
PROVIDER_CALL_LOG_KEY = "embedding:provider_call_log"

TENANT_ID = "tenant_e4_idempotency"
DOCUMENT_ID = "doc_e4_idempotency_001"
DOCUMENT_VERSION = "1"
LANGUAGE = "python"
CHUNKER_VERSION = "1.0.0"

TEST_SOURCE = """
class MyClass:
    def __init__(self, value):
        self.value = value

    def compute(self, x, y):
        return x + y + self.value
"""


def _engine_session():
    engine = create_engine(SYNC_DATABASE_URL, echo=False)
    return engine, sessionmaker(engine, expire_on_commit=False)


def _cleanup(session) -> None:
    session.execute(text("DELETE FROM embedding_jobs WHERE tenant_id = :t"), {"t": TENANT_ID})
    session.execute(text("DELETE FROM chunk_records WHERE tenant_id = :t"), {"t": TENANT_ID})
    session.commit()


def _chunk_document(source: str, chunker_version: str) -> List[Dict]:
    chunker = CodeChunker()
    # chunk_with_metadata uses ChunkIDGenerator with the provided chunker_version
    return chunker.chunk_with_metadata(
        tenant_id=TENANT_ID,
        document_id=DOCUMENT_ID,
        document_version=int(DOCUMENT_VERSION),
        source=source,
        language=LANGUAGE,
        chunker_version=chunker_version,
    )


def _insert_placeholders(session, chunks: List[Dict]) -> List[str]:
    ids = []
    for c in chunks:
        chunk_id = c["chunk_id"]
        ids.append(chunk_id)
        body = c.get("chunk_text") or c.get("text") or ""
        session.add(
            ChunkRecord(
                chunk_id=chunk_id,
                tenant_id=TENANT_ID,
                document_id=DOCUMENT_ID,
                document_version=int(DOCUMENT_VERSION),
                chunk_index=int(c.get("chunk_index", 0)),
                chunk_type=c.get("chunk_type") or "function_method",
                chunk_text=body,
                token_count=int(c.get("token_count") or max(1, len(body.split()))),
                start_byte=int(c.get("start_byte") or c.get("source_span_start") or 0),
                end_byte=int(c.get("end_byte") or c.get("source_span_end") or max(1, len(body))),
                chunker_version=CHUNKER_VERSION if "chunker_version" not in c else c.get("chunker_version", CHUNKER_VERSION),
                content_hash=c.get("content_hash") or uuid.uuid4().hex,
                chunk_content_checksum=c.get("chunk_content_checksum") or c.get("content_hash") or uuid.uuid4().hex,
                source_run_id="e4_idempotency",
                embedding_vector=None,
                embedding_model_version=None,
            )
        )
    session.commit()
    return ids


def _embed_via_celery(chunk_ids: List[str], chunks: List[Dict], redis_client) -> None:
    redis_client.delete(PROVIDER_CALL_LOG_KEY)
    job_ids = []
    for c in chunks:
        job_id = uuid.uuid4().hex
        job_ids.append(job_id)
        job_data = {
            "job_id": job_id,
            "tenant_id": TENANT_ID,
            "chunk_id": c["chunk_id"],
            "document_id": DOCUMENT_ID,
            "content_text": c.get("chunk_text") or "",
            "model_version_target": "v1",
        }
        async_result = embedding_task.apply_async(args=[job_data])
        print(f"   Enqueued job_id={job_id} celery_task_id={async_result.id} chunk_id={c['chunk_id'][:12]}...")

    deadline = time.time() + 120
    while time.time() < deadline:
        entries = [json.loads(x) for x in redis_client.lrange(PROVIDER_CALL_LOG_KEY, 0, -1)]
        seen = {e.get("job_id") for e in entries}
        if all(j in seen for j in job_ids):
            # wait briefly for commits
            time.sleep(0.3)
            return
        time.sleep(0.2)
    raise TimeoutError(f"Celery did not process all E4 jobs within timeout; seen={len(seen)}/{len(job_ids)}")


def _read_db_state(session) -> Tuple[Set[str], Dict[str, bool]]:
    rows = session.execute(
        select(ChunkRecord).where(ChunkRecord.tenant_id == TENANT_ID)
    ).scalars().all()
    ids = {r.chunk_id for r in rows}
    embedded = {r.chunk_id: (r.embedding_vector is not None and r.embedding_model_version is not None) for r in rows}
    return ids, embedded


def _one_pass(session, SessionLocal, redis_client, source: str, chunker_version: str, label: str):
    print(f"\n=== PASS {label}: chunk → insert → Celery embed → read-back ===")
    _cleanup(session)
    chunks = _chunk_document(source, chunker_version)
    for c in chunks:
        c["chunker_version"] = chunker_version
    print(f"   Chunked {len(chunks)} chunks")
    ids = _insert_placeholders(session, chunks)
    print(f"   Inserted {len(ids)} placeholder rows")
    _embed_via_celery(ids, chunks, redis_client)
    session.close()
    session = SessionLocal()
    db_ids, embedded = _read_db_state(session)
    if db_ids != set(ids):
        raise AssertionError(f"DB chunk_ids drifted from generated set: gen={sorted(ids)} db={sorted(db_ids)}")
    missing_emb = [cid for cid, ok in embedded.items() if not ok]
    if missing_emb:
        raise AssertionError(f"Chunks missing embedding after write path: {missing_emb}")
    print(f"   DB chunk_ids ({len(db_ids)}): {sorted(db_ids)}")
    print(f"   All chunks embedded via atomic UPDATE write path: YES")
    return session, db_ids, sorted(ids)


def test_e4_idempotency() -> bool:
    print("=" * 80)
    print("E4 IDEMPOTENCY VERIFICATION — REAL POSTGRES + CELERY WRITE PATH")
    print("=" * 80)
    print(f"DATABASE_URL={SYNC_DATABASE_URL}")

    engine, SessionLocal = _engine_session()
    session = SessionLocal()
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

    try:
        # Connectivity
        session.execute(text("SELECT 1"))
        print("[0] Postgres reachable")

        session, ids1, ordered1 = _one_pass(session, SessionLocal, redis_client, TEST_SOURCE, CHUNKER_VERSION, "1/3")
        session, ids2, ordered2 = _one_pass(session, SessionLocal, redis_client, TEST_SOURCE, CHUNKER_VERSION, "2/3")
        session, ids3, ordered3 = _one_pass(session, SessionLocal, redis_client, TEST_SOURCE, CHUNKER_VERSION, "3/3")

        print("\n[STABILITY] Comparing chunk_ids across 3 reprocess passes...")
        if ids1 == ids2 == ids3:
            print("   PASS: identical chunk_ids across all 3 passes (zero drift)")
            print(f"   Stable set: {sorted(ids1)}")
        else:
            print("   FAIL: chunk_ids drifted")
            print(f"   Pass1: {sorted(ids1)}")
            print(f"   Pass2: {sorted(ids2)}")
            print(f"   Pass3: {sorted(ids3)}")
            return False

        if ordered1 == ordered2 == ordered3:
            print("   PASS: ordered chunk_id lists also identical")
        else:
            print("   FAIL: ordered lists differ (set equal but order/content mapping drifted)")
            return False

        # Content-change divergence (chunk IDs must change; still exercise write path once)
        print("\n[CONTENT CHANGE] Modified document body must produce different chunk_ids...")
        modified = TEST_SOURCE + "\n    def new_method(self):\n        return 42\n"
        session, ids_mod, _ = _one_pass(session, SessionLocal, redis_client, modified, CHUNKER_VERSION, "content-change")
        if ids_mod != ids1:
            print(f"   PASS: content change diverged ({len(ids_mod)} ids vs {len(ids1)})")
            print(f"   New set: {sorted(ids_mod)}")
        else:
            print("   FAIL: content change did not change chunk_ids")
            return False

        # Chunker version bump divergence
        print("\n[CHUNKER VERSION] Bump chunker_version must produce different chunk_ids...")
        session, ids_ver, _ = _one_pass(session, SessionLocal, redis_client, TEST_SOURCE, "2.0.0", "chunker-version-bump")
        if ids_ver != ids1:
            print(f"   PASS: chunker_version bump diverged")
            print(f"   New set: {sorted(ids_ver)}")
        else:
            print("   FAIL: chunker_version bump did not change chunk_ids")
            return False

        _cleanup(session)
        print("\n" + "=" * 80)
        print("E4 IDEMPOTENCY VERIFICATION: PASSED")
        print("=" * 80)
        print("EVIDENCE:")
        print(f"- 3 reprocess passes identical chunk_ids: {sorted(ids1)}")
        print("- Each pass wrote embeddings via real Celery embedding_task (atomic conditional UPDATE)")
        print(f"- Content-change set: {sorted(ids_mod)}")
        print(f"- Chunker-version-bump set: {sorted(ids_ver)}")
        print(f"- DB: {SYNC_DATABASE_URL}")
        print(f"- Ended: {datetime.now(timezone.utc).isoformat()}")
        return True
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    try:
        ok = test_e4_idempotency()
        sys.exit(0 if ok else 1)
    except Exception as e:
        print(f"\nVerification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
