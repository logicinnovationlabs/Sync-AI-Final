"""In-memory activity store for Phase 1 signoff (and local dev)."""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import settings
from app.models.activity import (
    ActivityConfig,
    ActivityEvent,
    DocumentSignalResponse,
    PurgeResult,
    StoredEvent,
    UserSignalResponse,
    UserSignals,
)
from app.services.activity_store import ActivityStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ttl_for_event(event: ActivityEvent, config: ActivityConfig) -> int:
    if event.ttl_seconds is not None and event.ttl_seconds > 0:
        return int(event.ttl_seconds)
    if event.privacy_level in ("restricted", "confidential"):
        return int(config.high_privacy_retention_days) * 86400
    return int(config.retention_days) * 86400


class MockActivityStore(ActivityStore):
    """
    Tenant-isolated in-memory store.

    - Append-only activity_events with TTL
    - User signal cache rebuilt on ingest
    - Document popularity with privacy threshold enforced at query time
    - Optional in-process cache with TTL (simulates Redis namespacing)
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # tenant_id -> event_id -> StoredEvent
        self._events: Dict[str, Dict[str, StoredEvent]] = defaultdict(dict)
        # tenant_id -> ActivityConfig
        self._configs: Dict[str, ActivityConfig] = {}
        # tenant_id -> user_id -> UserSignalResponse
        self._user_cache: Dict[str, Dict[str, UserSignalResponse]] = defaultdict(dict)
        # signal response cache: (tenant, kind, id) -> (expires_at, payload)
        self._response_cache: Dict[Tuple[str, str, str], Tuple[float, Any]] = {}
        # ingest lag samples (seconds from event_time to signal update)
        self._lag_samples: List[float] = []
        self._ingest_count = 0
        self._dup_count = 0

    async def health(self) -> Tuple[bool, str]:
        with self._lock:
            n = sum(len(v) for v in self._events.values())
        return True, f"mock ok events={n}"

    async def ensure_tenant(self, tenant_id: str, config: Optional[ActivityConfig] = None) -> None:
        with self._lock:
            if tenant_id not in self._configs:
                self._configs[tenant_id] = config or ActivityConfig(
                    tenant_id=tenant_id,
                    privacy_threshold=settings.privacy_threshold,
                    retention_days=settings.retention_days,
                    high_privacy_retention_days=settings.high_privacy_retention_days,
                )
            elif config is not None:
                self._configs[tenant_id] = config
            self._events.setdefault(tenant_id, {})
            self._user_cache.setdefault(tenant_id, {})

    async def get_config(self, tenant_id: str) -> ActivityConfig:
        await self.ensure_tenant(tenant_id)
        with self._lock:
            return deepcopy(self._configs[tenant_id])

    async def set_config(self, config: ActivityConfig) -> None:
        with self._lock:
            self._configs[config.tenant_id] = config
            self._invalidate_tenant_cache(config.tenant_id)

    def _invalidate_tenant_cache(self, tenant_id: str) -> None:
        keys = [k for k in self._response_cache if k[0] == tenant_id]
        for k in keys:
            del self._response_cache[k]

    def _cache_get(self, tenant_id: str, kind: str, key: str) -> Optional[Any]:
        if not settings.cache_enabled:
            return None
        ck = (tenant_id, kind, key)
        entry = self._response_cache.get(ck)
        if not entry:
            return None
        expires, payload = entry
        if time.time() > expires:
            del self._response_cache[ck]
            return None
        return deepcopy(payload)

    def _cache_set(self, tenant_id: str, kind: str, key: str, payload: Any) -> None:
        if not settings.cache_enabled:
            return
        self._response_cache[(tenant_id, kind, key)] = (
            time.time() + settings.signal_cache_ttl_seconds,
            deepcopy(payload),
        )

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

        with self._lock:
            existing = self._events[tenant_id].get(event.event_id)
            if existing is not None:
                self._dup_count += 1
                return "already_processed"

            now = _as_utc(ingested_at or _utcnow())
            ttl = _ttl_for_event(event, config)
            stored = StoredEvent(
                event_id=event.event_id,
                tenant_id=tenant_id,
                actor_principal_id=event.actor_principal_id,
                object_id=event.object_id,
                event_type=event.event_type,
                source_system=event.source_system,
                event_time=_as_utc(event.event_time),
                session_id=event.session_id,
                context_json=event.context_json,
                privacy_level=event.privacy_level,
                ttl_seconds=ttl,
                ingested_at=now,
            )
            self._events[tenant_id][event.event_id] = stored
            self._ingest_count += 1

            # Signal update lag relative to event_time (for freshness monitoring)
            lag = max(0.0, (now - stored.event_time).total_seconds())
            self._lag_samples.append(lag)
            if len(self._lag_samples) > 5000:
                self._lag_samples = self._lag_samples[-2500:]

            self._recompute_user_locked(tenant_id, event.actor_principal_id, now)
            # Collaborators on same object also benefit from refreshed heatmap later
            self._invalidate_tenant_cache(tenant_id)
            return "ingested"

    async def get_event(self, tenant_id: str, event_id: str) -> Optional[StoredEvent]:
        with self._lock:
            ev = self._events.get(tenant_id, {}).get(event_id)
            return deepcopy(ev) if ev else None

    async def list_events(
        self,
        tenant_id: str,
        *,
        object_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        include_expired: bool = True,
    ) -> List[StoredEvent]:
        now = _utcnow()
        with self._lock:
            rows = list(self._events.get(tenant_id, {}).values())
        out: List[StoredEvent] = []
        for ev in rows:
            if object_id and ev.object_id != object_id:
                continue
            if actor_id and ev.actor_principal_id != actor_id:
                continue
            if not include_expired:
                expiry = ev.ingested_at + timedelta(seconds=ev.ttl_seconds)
                if now >= expiry:
                    continue
            out.append(deepcopy(ev))
        return out

    def _active_events_locked(
        self, tenant_id: str, *, now: Optional[datetime] = None
    ) -> List[StoredEvent]:
        now = _as_utc(now or _utcnow())
        active: List[StoredEvent] = []
        for ev in self._events.get(tenant_id, {}).values():
            expiry = ev.ingested_at + timedelta(seconds=ev.ttl_seconds)
            if now < expiry:
                active.append(ev)
        return active

    def _recompute_user_locked(
        self, tenant_id: str, user_id: str, now: Optional[datetime] = None
    ) -> UserSignalResponse:
        now = _as_utc(now or _utcnow())
        events = [
            e
            for e in self._active_events_locked(tenant_id, now=now)
            if e.actor_principal_id == user_id
        ]
        events.sort(key=lambda e: e.event_time, reverse=True)

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
            day = ev.event_time.strftime("%Y-%m-%d")
            heatmap[day] += 1
            if last_active is None or ev.event_time > last_active:
                last_active = ev.event_time
            if ev.event_type == "view":
                view_counts[ev.object_id] += 1
            elif ev.event_type == "edit":
                edit_counts[ev.object_id] += 1
            elif ev.event_type == "authored":
                authored.add(ev.object_id)

        # Collaborators: other actors on same objects
        objects = {e.object_id for e in events}
        collab: Counter = Counter()
        for ev in self._active_events_locked(tenant_id, now=now):
            if ev.object_id in objects and ev.actor_principal_id != user_id:
                collab[ev.actor_principal_id] += 1

        signals = UserSignals(
            last_active=last_active,
            top_viewed_docs=[d for d, _ in view_counts.most_common(10)],
            top_edited_docs=[d for d, _ in edit_counts.most_common(10)],
            authored_docs=sorted(authored),
            frequent_collaborators=[u for u, _ in collab.most_common(10)],
            preferred_sources=[s for s, _ in sources.most_common(5)],
            activity_heatmap=dict(heatmap),
            event_counts_by_type=dict(type_counts),
        )
        resp = UserSignalResponse(
            user_id=user_id,
            tenant_id=tenant_id,
            signals=signals,
            updated_at=now,
            freshness_s=0.0,
        )
        self._user_cache[tenant_id][user_id] = resp
        return resp

    async def get_user_signals(self, tenant_id: str, user_id: str) -> UserSignalResponse:
        await self.ensure_tenant(tenant_id)
        cached = self._cache_get(tenant_id, "user", user_id)
        if cached is not None:
            return UserSignalResponse.model_validate(cached)

        with self._lock:
            resp = self._recompute_user_locked(tenant_id, user_id)
            # freshness: age of newest event for this user vs now
            events = [
                e
                for e in self._active_events_locked(tenant_id)
                if e.actor_principal_id == user_id
            ]
            if events:
                newest_ingest = max(e.ingested_at for e in events)
                resp.freshness_s = max(0.0, (_utcnow() - newest_ingest).total_seconds())
            else:
                resp.freshness_s = None
            out = deepcopy(resp)

        self._cache_set(tenant_id, "user", user_id, out.model_dump(mode="json"))
        return out

    def _document_stats_locked(
        self, tenant_id: str, document_id: str, *, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        now = _as_utc(now or _utcnow())
        window_start = now - timedelta(days=settings.popularity_window_days)
        events = [
            e
            for e in self._active_events_locked(tenant_id, now=now)
            if e.object_id == document_id and e.event_time >= window_start
        ]
        viewers: Set[str] = set()
        views = 0
        last_viewed: Optional[datetime] = None
        for ev in events:
            if ev.event_type == "view":
                views += 1
                viewers.add(ev.actor_principal_id)
                if last_viewed is None or ev.event_time > last_viewed:
                    last_viewed = ev.event_time
            else:
                # non-view activity still counts toward distinct actors for collab popularity
                viewers.add(ev.actor_principal_id)
        return {
            "distinct_actors": len(viewers),
            "total_views": views,
            "last_viewed": last_viewed,
            "window_start": window_start,
            "updated_at": now,
        }

    async def get_document_signals(
        self, tenant_id: str, document_id: str
    ) -> DocumentSignalResponse:
        await self.ensure_tenant(tenant_id)
        cached = self._cache_get(tenant_id, "doc", document_id)
        if cached is not None:
            return DocumentSignalResponse.model_validate(cached)

        config = await self.get_config(tenant_id)
        with self._lock:
            stats = self._document_stats_locked(tenant_id, document_id)
            distinct = int(stats["distinct_actors"])
            threshold = config.privacy_threshold

            if distinct < threshold:
                # Never leak numeric aggregates below threshold
                resp = DocumentSignalResponse(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    privacy_protected=True,
                    popularity_score=None,
                    total_views=None,
                    distinct_viewers=None,
                    last_viewed=None,
                    updated_at=stats["updated_at"],
                    window_days=settings.popularity_window_days,
                )
            else:
                # Normalize popularity: log-scaled views capped at 1.0
                views = int(stats["total_views"])
                score = min(1.0, math.log1p(views) / math.log1p(100))
                resp = DocumentSignalResponse(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    privacy_protected=False,
                    popularity_score=round(score, 4),
                    total_views=views,
                    distinct_viewers=distinct,
                    last_viewed=stats["last_viewed"],
                    updated_at=stats["updated_at"],
                    window_days=settings.popularity_window_days,
                )

        self._cache_set(tenant_id, "doc", document_id, resp.model_dump(mode="json"))
        return resp

    async def purge_expired(self, *, now: Optional[datetime] = None) -> PurgeResult:
        now = _as_utc(now or _utcnow())
        purged = 0
        tenants: Set[str] = set()
        with self._lock:
            for tenant_id, events in list(self._events.items()):
                expired_ids = [
                    eid
                    for eid, ev in events.items()
                    if now >= (ev.ingested_at + timedelta(seconds=ev.ttl_seconds))
                ]
                for eid in expired_ids:
                    del events[eid]
                    purged += 1
                    tenants.add(tenant_id)
                if expired_ids:
                    self._invalidate_tenant_cache(tenant_id)
                    # Rebuild user caches from remaining events
                    actors = {e.actor_principal_id for e in events.values()}
                    for actor in actors:
                        self._recompute_user_locked(tenant_id, actor, now)
                    # Clear caches for users with no remaining events
                    stale_users = [
                        uid
                        for uid in list(self._user_cache.get(tenant_id, {}))
                        if uid not in actors
                    ]
                    for uid in stale_users:
                        del self._user_cache[tenant_id][uid]

        return PurgeResult(
            purged_events=purged,
            tenants_touched=sorted(tenants),
            aggregates_rebuilt=purged,
        )

    async def clear_tenant(self, tenant_id: str) -> None:
        with self._lock:
            self._events.pop(tenant_id, None)
            self._user_cache.pop(tenant_id, None)
            self._configs.pop(tenant_id, None)
            self._invalidate_tenant_cache(tenant_id)

    async def recompute_signals(self, tenant_id: str) -> None:
        await self.ensure_tenant(tenant_id)
        with self._lock:
            actors = {
                e.actor_principal_id for e in self._active_events_locked(tenant_id)
            }
            for actor in actors:
                self._recompute_user_locked(tenant_id, actor)
            self._invalidate_tenant_cache(tenant_id)

    async def metrics_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            samples = list(self._lag_samples)
            event_count = sum(len(v) for v in self._events.values())
        p95 = None
        if samples:
            ordered = sorted(samples)
            idx = min(len(ordered) - 1, max(0, int(math.ceil(0.95 * len(ordered)) - 1)))
            p95 = ordered[idx]
        return {
            "ingest_count": self._ingest_count,
            "duplicate_count": self._dup_count,
            "event_count": event_count,
            "ingest_lag_p95_s": p95,
            "cache_entries": len(self._response_cache),
        }
