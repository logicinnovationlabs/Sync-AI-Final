"""Tenant-scoped episodic memory backed by the control-plane Postgres."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import psycopg
from psycopg.rows import dict_row

from app.services.assistant.domain.models import SessionContext, TurnRecord

logger = logging.getLogger(__name__)


def _sync_postgres_dsn() -> str:
    """Resolve a psycopg DSN. Automatically enforces transaction pooler (6543) for Supabase."""
    explicit = (
        os.getenv("ORCHESTRATOR_DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("SUPABASE_POOLER_URL")
        or ""
    ).strip()
    if explicit:
        dsn = explicit.replace("postgresql+asyncpg://", "postgresql://")
    else:
        from app.core.config import settings

        url = (settings.control_plane_database_url or settings.supabase_db_url or "").strip()
        if url:
            dsn = url.replace("postgresql+asyncpg://", "postgresql://")
        else:
            user = quote_plus(str(settings.db_user))
            password = quote_plus(str(settings.db_password))
            dsn = f"postgresql://{user}:{password}@{settings.db_host}:5432/{settings.db_name}"

    # Supabase pooler on port 5432 (Session mode) is limited to 15 concurrent clients (EMAXCONNSESSION).
    # Port 6543 is Transaction mode (PgBouncer/Supavisor), which handles high concurrent traffic.
    if "pooler.supabase.com" in dsn:
        if ":5432" in dsn:
            dsn = dsn.replace(":5432", ":6543")
        elif ":6543" not in dsn and not any(f":{p}" in dsn for p in range(1000, 65535)):
            # If no port was specified, add :6543
            parts = dsn.split("@", 1)
            if len(parts) == 2:
                host_and_rest = parts[1].split("/", 1)
                host_port = f"{host_and_rest[0]}:6543"
                rest = f"/{host_and_rest[1]}" if len(host_and_rest) > 1 else ""
                dsn = f"{parts[0]}@{host_port}{rest}"
    return dsn


class EpisodicMemoryStore:
    """
    Session + turn memory keyed by (tenant_id, session_id).

    Multi-tenant isolation is enforced at every read/write — tenant_id is a
    required predicate, never optional.
    Includes in-memory fallback cache to ensure zero chat failures during
    database connection limits or transient cloud pooler outages.
    """

    def __init__(self, dsn: Optional[str] = None) -> None:
        raw_dsn = dsn or _sync_postgres_dsn()
        if "pooler.supabase.com" in raw_dsn and ":5432" in raw_dsn:
            raw_dsn = raw_dsn.replace(":5432", ":6543")
        self.dsn = raw_dsn
        self._fallback_sessions: Dict[str, SessionContext] = {}
        self._fallback_memory: Dict[str, Dict[str, Any]] = {}

    def _connect(self) -> psycopg.Connection:
        """Connect to Postgres with prepared-statements disabled for PgBouncer/Supavisor transaction pooler."""
        dsn = self.dsn
        if "pooler.supabase.com" in dsn and ":5432" in dsn:
            dsn = dsn.replace(":5432", ":6543")
            self.dsn = dsn

        try:
            return psycopg.connect(
                dsn,
                row_factory=dict_row,
                connect_timeout=5,
                prepare_threshold=None,
            )
        except Exception as primary_exc:
            # If failed on session port 5432, try fallback to transaction port 6543
            if ":5432" in dsn and "pooler.supabase.com" in dsn:
                fallback_dsn = dsn.replace(":5432", ":6543")
                try:
                    conn = psycopg.connect(
                        fallback_dsn,
                        row_factory=dict_row,
                        connect_timeout=5,
                        prepare_threshold=None,
                    )
                    self.dsn = fallback_dsn
                    return conn
                except Exception:
                    pass
            raise primary_exc

    def ensure_schema(self) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS orchestrator_sessions (
                            tenant_id   TEXT NOT NULL,
                            user_id     TEXT NOT NULL,
                            session_id  TEXT NOT NULL,
                            history_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            intent_stack JSONB NOT NULL DEFAULT '[]'::jsonb,
                            last_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (tenant_id, session_id)
                        );
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS orchestrator_memory (
                            tenant_id   TEXT NOT NULL,
                            user_id     TEXT NOT NULL,
                            memory_key  TEXT NOT NULL,
                            memory_value JSONB NOT NULL,
                            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (tenant_id, user_id, memory_key)
                        );
                        """
                    )
                conn.commit()
        except Exception as exc:
            logger.warning("[EpisodicMemoryStore] ensure_schema failed (using fallback if needed): %s", exc)

    def load_session(self, tenant_id: str, session_id: str) -> Optional[SessionContext]:
        key = f"{tenant_id}:{session_id}"
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT tenant_id, user_id, session_id, history_json, intent_stack, last_document_ids
                        FROM orchestrator_sessions
                        WHERE tenant_id = %s AND session_id = %s
                        """,
                        (tenant_id, session_id),
                    )
                    row = cur.fetchone()
            if not row:
                return self._fallback_sessions.get(key)
            history = [TurnRecord.model_validate(t) for t in (row["history_json"] or [])]
            ctx = SessionContext(
                tenant_id=row["tenant_id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                history=history,
                intent_stack=list(row["intent_stack"] or []),
                last_document_ids=list(row["last_document_ids"] or []),
            )
            # Sync to fallback cache
            self._fallback_sessions[key] = ctx
            return ctx
        except Exception as exc:
            logger.warning("[EpisodicMemoryStore] load_session DB error (%s), using in-memory store", exc)
            return self._fallback_sessions.get(key)

    def save_session(self, ctx: SessionContext) -> None:
        key = f"{ctx.tenant_id}:{ctx.session_id}"
        self._fallback_sessions[key] = ctx
        history = [t.model_dump() for t in ctx.history]
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO orchestrator_sessions
                            (tenant_id, user_id, session_id, history_json, intent_stack, last_document_ids, updated_at)
                        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, NOW())
                        ON CONFLICT (tenant_id, session_id) DO UPDATE SET
                            user_id = EXCLUDED.user_id,
                            history_json = EXCLUDED.history_json,
                            intent_stack = EXCLUDED.intent_stack,
                            last_document_ids = EXCLUDED.last_document_ids,
                            updated_at = NOW()
                        """,
                        (
                            ctx.tenant_id,
                            ctx.user_id,
                            ctx.session_id,
                            json.dumps(history),
                            json.dumps(ctx.intent_stack),
                            json.dumps(ctx.last_document_ids),
                        ),
                    )
                conn.commit()
        except Exception as exc:
            logger.warning("[EpisodicMemoryStore] save_session DB error (%s), saved to in-memory fallback", exc)

    def put_memory(self, tenant_id: str, user_id: str, key: str, value: Dict[str, Any]) -> None:
        mem_key = f"{tenant_id}:{user_id}:{key}"
        self._fallback_memory[mem_key] = value
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO orchestrator_memory (tenant_id, user_id, memory_key, memory_value, updated_at)
                        VALUES (%s, %s, %s, %s::jsonb, NOW())
                        ON CONFLICT (tenant_id, user_id, memory_key) DO UPDATE SET
                            memory_value = EXCLUDED.memory_value,
                            updated_at = NOW()
                        """,
                        (tenant_id, user_id, key, json.dumps(value)),
                    )
                conn.commit()
        except Exception as exc:
            logger.warning("[EpisodicMemoryStore] put_memory DB error (%s), stored in in-memory fallback", exc)

    def get_memory(self, tenant_id: str, user_id: str, key: str) -> Optional[Dict[str, Any]]:
        mem_key = f"{tenant_id}:{user_id}:{key}"
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT memory_value FROM orchestrator_memory
                        WHERE tenant_id = %s AND user_id = %s AND memory_key = %s
                        """,
                        (tenant_id, user_id, key),
                    )
                    row = cur.fetchone()
            if not row:
                return self._fallback_memory.get(mem_key)
            val = row["memory_value"]
            return dict(val) if isinstance(val, dict) else {"value": val}
        except Exception as exc:
            logger.warning("[EpisodicMemoryStore] get_memory DB error (%s), using in-memory fallback", exc)
            return self._fallback_memory.get(mem_key)

    def list_sessions_for_user(
        self, tenant_id: str, user_id: str, *, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Newest-first session summaries for one principal. Tenant-scoped."""
        out: List[Dict[str, Any]] = []
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT session_id, user_id, history_json, updated_at
                        FROM orchestrator_sessions
                        WHERE tenant_id = %s AND user_id = %s
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                        (tenant_id, user_id, int(limit)),
                    )
                    rows = cur.fetchall()
            for row in rows:
                history = row.get("history_json") or []
                title = ""
                if isinstance(history, list):
                    for turn in history:
                        if isinstance(turn, dict) and turn.get("role") == "user":
                            title = str(turn.get("content") or "").strip()
                            break
                updated = row.get("updated_at")
                out.append(
                    {
                        "session_id": row["session_id"],
                        "title": title[:80] if title else "New chat",
                        "turn_count": len(history) if isinstance(history, list) else 0,
                        "updated_at": updated.isoformat() if updated is not None else None,
                    }
                )
            return out
        except Exception as exc:
            logger.warning("[EpisodicMemoryStore] list_sessions_for_user DB error (%s), using fallback cache", exc)
            # Fallback to cached in-memory sessions for this user/tenant
            for key, ctx in self._fallback_sessions.items():
                if ctx.tenant_id == tenant_id and ctx.user_id == user_id:
                    title = ""
                    for turn in ctx.history:
                        if turn.role == "user":
                            title = str(turn.content or "").strip()
                            break
                    out.append(
                        {
                            "session_id": ctx.session_id,
                            "title": title[:80] if title else "New chat",
                            "turn_count": len(ctx.history),
                            "updated_at": None,
                        }
                    )
            return out[:limit]

    def list_sessions_for_tenant(self, tenant_id: str) -> List[str]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT session_id FROM orchestrator_sessions WHERE tenant_id = %s",
                        (tenant_id,),
                    )
                    rows = cur.fetchall()
            return [r["session_id"] for r in rows]
        except Exception as exc:
            logger.warning("[EpisodicMemoryStore] list_sessions_for_tenant DB error (%s), using fallback cache", exc)
            return [ctx.session_id for ctx in self._fallback_sessions.values() if ctx.tenant_id == tenant_id]
