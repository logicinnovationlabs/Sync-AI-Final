"""Tenant-scoped episodic memory backed by Postgres (:5433)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from assistant_orchestrator.domain.models import SessionContext, TurnRecord

logger = logging.getLogger(__name__)

DEFAULT_DSN = os.getenv(
    "ORCHESTRATOR_DATABASE_URL",
    "postgresql://postgres:verify@127.0.0.1:5433/block_e",
)


class EpisodicMemoryStore:
    """
    Session + turn memory keyed by (tenant_id, session_id).

    Multi-tenant isolation is enforced at every read/write — tenant_id is a
    required predicate, never optional.
    """

    def __init__(self, dsn: Optional[str] = None) -> None:
        self.dsn = dsn or DEFAULT_DSN

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def ensure_schema(self) -> None:
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

    def load_session(self, tenant_id: str, session_id: str) -> Optional[SessionContext]:
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
            return None
        history = [TurnRecord.model_validate(t) for t in (row["history_json"] or [])]
        return SessionContext(
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            history=history,
            intent_stack=list(row["intent_stack"] or []),
            last_document_ids=list(row["last_document_ids"] or []),
        )

    def save_session(self, ctx: SessionContext) -> None:
        history = [t.model_dump() for t in ctx.history]
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

    def put_memory(self, tenant_id: str, user_id: str, key: str, value: Dict[str, Any]) -> None:
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

    def get_memory(self, tenant_id: str, user_id: str, key: str) -> Optional[Dict[str, Any]]:
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
            return None
        val = row["memory_value"]
        return dict(val) if isinstance(val, dict) else {"value": val}

    def list_sessions_for_tenant(self, tenant_id: str) -> List[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT session_id FROM orchestrator_sessions WHERE tenant_id = %s",
                    (tenant_id,),
                )
                rows = cur.fetchall()
        return [r["session_id"] for r in rows]
