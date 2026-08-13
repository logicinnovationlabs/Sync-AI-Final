"""Postgres-backed activity store (Phase 2 / Block D integration)."""

from __future__ import annotations

import json
import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.config import settings
from app.models.activity import (
    ActivityConfig,
    ActivityEvent,
    DocumentSignalResponse,
    PurgeResult,
    StoredEvent,
    UserSignalResponse,
    UserSignals,
)
from app.services.signals.store import ActivityStore

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS activity_config (
    tenant_id TEXT PRIMARY KEY,
    privacy_threshold INTEGER NOT NULL DEFAULT 5,
    retention_days INTEGER NOT NULL DEFAULT 90,
    high_privacy_retention_days INTEGER NOT NULL DEFAULT 30,
    enable_per_source_disablement BOOLEAN NOT NULL DEFAULT FALSE,
    disabled_sources JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS activity_events (
    event_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    actor_principal_id TEXT NOT NULL,
    object_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_system TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    session_id TEXT,
    context_json JSONB,
    privacy_level TEXT NOT NULL DEFAULT 'public',
    ttl_seconds INTEGER NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_activity_events_tenant_object
    ON activity_events (tenant_id, object_id);
CREATE INDEX IF NOT EXISTS idx_activity_events_tenant_actor
    ON activity_events (tenant_id, actor_principal_id);
CREATE INDEX IF NOT EXISTS idx_activity_events_ingested
    ON activity_events (tenant_id, ingested_at);
"""


class PostgresActivityStore(ActivityStore):
    """Append-only Postgres store with query-time privacy threshold."""

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "psycopg is required for SIGNALS_BACKEND=postgres"
            ) from exc

        self._psycopg = psycopg
        self._dict_row = dict_row
        self._url = database_url
        self._ensure_schema()

    def _conn(self):
        return self._psycopg.connect(self._url, row_factory=self._dict_row)

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()

    async def health(self) -> Tuple[bool, str]:
        try:
            with self._conn() as conn:
                row = conn.execute("SELECT COUNT(*) AS n FROM activity_events").fetchone()
            return True, f"postgres ok events={row['n']}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _default_config(self, tenant_id: str) -> ActivityConfig:
        return ActivityConfig(
            tenant_id=tenant_id,
            privacy_threshold=settings.privacy_threshold,
            retention_days=settings.retention_days,
            high_privacy_retention_days=settings.high_privacy_retention_days,
        )

    async def ensure_tenant(self, tenant_id: str, config: Optional[ActivityConfig] = None) -> None:
        cfg = config or self._default_config(tenant_id)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO activity_config (
                    tenant_id, privacy_threshold, retention_days,
                    high_privacy_retention_days, enable_per_source_disablement, disabled_sources
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (
                    cfg.tenant_id,
                    cfg.privacy_threshold,
                    cfg.retention_days,
                    cfg.high_privacy_retention_days,
                    cfg.enable_per_source_disablement,
                    json.dumps(cfg.disabled_sources),
                ),
            )
            if config is not None:
                conn.execute(
                    """
                    UPDATE activity_config SET
                        privacy_threshold=%s,
                        retention_days=%s,
                        high_privacy_retention_days=%s,
                        enable_per_source_disablement=%s,
                        disabled_sources=%s::jsonb
                    WHERE tenant_id=%s
                    """,
                    (
                        config.privacy_threshold,
                        config.retention_days,
                        config.high_privacy_retention_days,
                        config.enable_per_source_disablement,
                        json.dumps(config.disabled_sources),
                        tenant_id,
                    ),
                )
            conn.commit()

    async def get_config(self, tenant_id: str) -> ActivityConfig:
        await self.ensure_tenant(tenant_id)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM activity_config WHERE tenant_id=%s", (tenant_id,)
            ).fetchone()
        disabled = row["disabled_sources"] or []
        if isinstance(disabled, str):
            disabled = json.loads(disabled)
        return ActivityConfig(
            tenant_id=row["tenant_id"],
            privacy_threshold=row["privacy_threshold"],
            retention_days=row["retention_days"],
            high_privacy_retention_days=row["high_privacy_retention_days"],
            enable_per_source_disablement=row["enable_per_source_disablement"],
            disabled_sources=list(disabled),
        )

    async def set_config(self, config: ActivityConfig) -> None:
        await self.ensure_tenant(config.tenant_id, config)

    def _ttl(self, event: ActivityEvent, config: ActivityConfig) -> int:
        if event.ttl_seconds is not None and event.ttl_seconds > 0:
            return int(event.ttl_seconds)
        if event.privacy_level in ("restricted", "confidential"):
            return int(config.high_privacy_retention_days) * 86400
        return int(config.retention_days) * 86400

    async def ingest_event(
        self,
        tenant_id: str,
        event: ActivityEvent,
        *,
        ingested_at: Optional[datetime] = None,
    ) -> str:
        await self.ensure_tenant(tenant_id)
        config = await self.get_config(tenant_id)
        if config.enable_per_source_disablement and event.source_system in config.disabled_sources:
            raise ValueError(f"source_system disabled for tenant: {event.source_system}")

        now = _as_utc(ingested_at or _utcnow())
        ttl = self._ttl(event, config)
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM activity_events WHERE tenant_id=%s AND event_id=%s",
                (tenant_id, event.event_id),
            ).fetchone()
            if existing:
                return "already_processed"
            conn.execute(
                """
                INSERT INTO activity_events (
                    event_id, tenant_id, actor_principal_id, object_id, event_type,
                    source_system, event_time, session_id, context_json, privacy_level,
                    ttl_seconds, ingested_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                """,
                (
                    event.event_id,
                    tenant_id,
                    event.actor_principal_id,
                    event.object_id,
                    event.event_type,
                    event.source_system,
                    _as_utc(event.event_time),
                    event.session_id,
                    json.dumps(event.context_json or {}),
                    event.privacy_level,
                    ttl,
                    now,
                ),
            )
            conn.commit()
        return "ingested"

    def _row_to_event(self, row: Dict[str, Any]) -> StoredEvent:
        ctx = row.get("context_json") or {}
        if isinstance(ctx, str):
            ctx = json.loads(ctx)
        return StoredEvent(
            event_id=row["event_id"],
            tenant_id=row["tenant_id"],
            actor_principal_id=row["actor_principal_id"],
            object_id=row["object_id"],
            event_type=row["event_type"],
            source_system=row["source_system"],
            event_time=_as_utc(row["event_time"]),
            session_id=row.get("session_id"),
            context_json=ctx,
            privacy_level=row.get("privacy_level") or "public",
            ttl_seconds=int(row["ttl_seconds"]),
            ingested_at=_as_utc(row["ingested_at"]),
        )

    async def get_event(self, tenant_id: str, event_id: str) -> Optional[StoredEvent]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM activity_events WHERE tenant_id=%s AND event_id=%s",
                (tenant_id, event_id),
            ).fetchone()
        return self._row_to_event(row) if row else None

    async def list_events(
        self,
        tenant_id: str,
        *,
        object_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        include_expired: bool = True,
    ) -> List[StoredEvent]:
        sql = "SELECT * FROM activity_events WHERE tenant_id=%s"
        params: List[Any] = [tenant_id]
        if object_id:
            sql += " AND object_id=%s"
            params.append(object_id)
        if actor_id:
            sql += " AND actor_principal_id=%s"
            params.append(actor_id)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        now = _utcnow()
        out: List[StoredEvent] = []
        for row in rows:
            ev = self._row_to_event(row)
            if not include_expired:
                if now >= ev.ingested_at + timedelta(seconds=ev.ttl_seconds):
                    continue
            out.append(ev)
        return out

    def _active_sql_filter(self) -> str:
        return "ingested_at + (ttl_seconds * INTERVAL '1 second') > NOW()"

    async def get_user_signals(self, tenant_id: str, user_id: str) -> UserSignalResponse:
        await self.ensure_tenant(tenant_id)
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM activity_events
                WHERE tenant_id=%s AND actor_principal_id=%s
                  AND {self._active_sql_filter()}
                ORDER BY event_time DESC
                """,
                (tenant_id, user_id),
            ).fetchall()
            events = [self._row_to_event(r) for r in rows]
            objects = {e.object_id for e in events}
            collab: Counter = Counter()
            if objects:
                collab_rows = conn.execute(
                    f"""
                    SELECT actor_principal_id, COUNT(*) AS c
                    FROM activity_events
                    WHERE tenant_id=%s
                      AND object_id = ANY(%s)
                      AND actor_principal_id <> %s
                      AND {self._active_sql_filter()}
                    GROUP BY actor_principal_id
                    """,
                    (tenant_id, list(objects), user_id),
                ).fetchall()
                for r in collab_rows:
                    collab[r["actor_principal_id"]] = int(r["c"])

        view_counts: Counter = Counter()
        edit_counts: Counter = Counter()
        authored: Set[str] = set()
        sources: Counter = Counter()
        type_counts: Counter = Counter()
        heatmap: Counter = Counter()
        last_active: Optional[datetime] = None
        for ev in events:
            type_counts[ev.event_type] += 1
            sources[ev.source_system] += 1
            heatmap[ev.event_time.strftime("%Y-%m-%d")] += 1
            if last_active is None or ev.event_time > last_active:
                last_active = ev.event_time
            if ev.event_type == "view":
                view_counts[ev.object_id] += 1
            elif ev.event_type == "edit":
                edit_counts[ev.object_id] += 1
            elif ev.event_type == "authored":
                authored.add(ev.object_id)

        now = _utcnow()
        freshness = None
        if events:
            freshness = max(0.0, (now - max(e.ingested_at for e in events)).total_seconds())

        return UserSignalResponse(
            user_id=user_id,
            tenant_id=tenant_id,
            signals=UserSignals(
                last_active=last_active,
                top_viewed_docs=[d for d, _ in view_counts.most_common(10)],
                top_edited_docs=[d for d, _ in edit_counts.most_common(10)],
                authored_docs=sorted(authored),
                frequent_collaborators=[u for u, _ in collab.most_common(10)],
                preferred_sources=[s for s, _ in sources.most_common(5)],
                activity_heatmap=dict(heatmap),
                event_counts_by_type=dict(type_counts),
            ),
            updated_at=now,
            freshness_s=freshness,
        )

    async def get_document_signals(
        self, tenant_id: str, document_id: str
    ) -> DocumentSignalResponse:
        await self.ensure_tenant(tenant_id)
        config = await self.get_config(tenant_id)
        window_days = settings.popularity_window_days
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM activity_events
                WHERE tenant_id=%s AND object_id=%s
                  AND event_time >= NOW() - (%s * INTERVAL '1 day')
                  AND {self._active_sql_filter()}
                """,
                (tenant_id, document_id, window_days),
            ).fetchall()
        events = [self._row_to_event(r) for r in rows]
        viewers: Set[str] = set()
        views = 0
        last_viewed: Optional[datetime] = None
        for ev in events:
            viewers.add(ev.actor_principal_id)
            if ev.event_type == "view":
                views += 1
                if last_viewed is None or ev.event_time > last_viewed:
                    last_viewed = ev.event_time

        now = _utcnow()
        distinct = len(viewers)
        if distinct < config.privacy_threshold:
            return DocumentSignalResponse(
                document_id=document_id,
                tenant_id=tenant_id,
                privacy_protected=True,
                popularity_score=None,
                total_views=None,
                distinct_viewers=None,
                last_viewed=None,
                updated_at=now,
                window_days=window_days,
            )

        score = min(1.0, math.log1p(views) / math.log1p(100))
        return DocumentSignalResponse(
            document_id=document_id,
            tenant_id=tenant_id,
            privacy_protected=False,
            popularity_score=round(score, 4),
            total_views=views,
            distinct_viewers=distinct,
            last_viewed=last_viewed,
            updated_at=now,
            window_days=window_days,
        )

    async def purge_expired(self, *, now: Optional[datetime] = None) -> PurgeResult:
        # Use DB clock unless an explicit now is provided for tests
        with self._conn() as conn:
            if now is None:
                rows = conn.execute(
                    """
                    DELETE FROM activity_events
                    WHERE ingested_at + (ttl_seconds * INTERVAL '1 second') <= NOW()
                    RETURNING tenant_id
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    DELETE FROM activity_events
                    WHERE ingested_at + (ttl_seconds * INTERVAL '1 second') <= %s
                    RETURNING tenant_id
                    """,
                    (_as_utc(now),),
                ).fetchall()
            conn.commit()
        tenants = sorted({r["tenant_id"] for r in rows})
        return PurgeResult(
            purged_events=len(rows),
            tenants_touched=tenants,
            aggregates_rebuilt=len(rows),
        )

    async def clear_tenant(self, tenant_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM activity_events WHERE tenant_id=%s", (tenant_id,))
            conn.execute("DELETE FROM activity_config WHERE tenant_id=%s", (tenant_id,))
            conn.commit()

    async def recompute_signals(self, tenant_id: str) -> None:
        # Query-time aggregation — nothing durable to rebuild.
        return None
