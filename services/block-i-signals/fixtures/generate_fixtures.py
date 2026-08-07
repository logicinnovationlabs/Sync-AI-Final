"""Generate Block Z-shaped activity fixtures for Block I signoff (I1-I3)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
NOW = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


TENANTS = {
    "tenant-a": {
        "actors": [f"p-user-{i:03d}" for i in range(1, 16)],
        "docs": [f"doc-a-{i:03d}" for i in range(1, 11)],
        "sources": ["confluence", "github", "slack", "gdrive"],
    },
    "tenant-b": {
        "actors": [f"p-user-b-{i:03d}" for i in range(1, 8)],
        "docs": [f"doc-b-{i:03d}" for i in range(1, 6)],
        "sources": ["jira", "slack"],
    },
    "tenant-c": {
        "actors": [f"p-user-c-{i:03d}" for i in range(1, 6)],
        "docs": [f"doc-c-{i:03d}" for i in range(1, 4)],
        "sources": ["notion"],
    },
}

EVENT_TYPES = ["view", "edit", "authored", "commented_on", "referenced", "worked_on"]


def build_events() -> dict:
    events = []
    eid = 0
    for tenant, meta in TENANTS.items():
        actors = meta["actors"]
        docs = meta["docs"]
        sources = meta["sources"]
        for i in range(25 if tenant == "tenant-a" else 15):
            eid += 1
            actor = actors[i % len(actors)]
            doc = docs[i % len(docs)]
            etype = EVENT_TYPES[i % len(EVENT_TYPES)]
            source = sources[i % len(sources)]
            t = NOW - timedelta(minutes=5 * i)
            events.append(
                {
                    "event_id": f"evt-{tenant}-{eid:04d}",
                    "tenant_id": tenant,
                    "actor_principal_id": actor,
                    "object_id": doc,
                    "event_type": etype if etype != "view" or i % 2 == 0 else "view",
                    "source_system": source,
                    "event_time": _iso(t),
                    "session_id": f"sess-{tenant}-{i // 3}",
                    "context_json": {"path": f"/docs/{doc}"},
                    "privacy_level": "public" if i % 7 else "restricted",
                }
            )
    for i, actor in enumerate(TENANTS["tenant-a"]["actors"][:10]):
        eid += 1
        events.append(
            {
                "event_id": f"evt-popular-{i:04d}",
                "tenant_id": "tenant-a",
                "actor_principal_id": actor,
                "object_id": "doc-a-001",
                "event_type": "view",
                "source_system": "confluence",
                "event_time": _iso(NOW - timedelta(minutes=i)),
                "session_id": f"sess-pop-{i}",
                "context_json": {"page": "/docs/deployment"},
                "privacy_level": "public",
            }
        )
    return {
        "version": "v1",
        "generated_at": _iso(NOW),
        "description": "50+ activity events across 3 tenants for Block I",
        "events": events,
    }


def build_privacy_cases() -> dict:
    cases = []
    threshold = 5
    for count, doc in [(1, "doc-priv-001"), (3, "doc-priv-003"), (5, "doc-priv-005"), (10, "doc-priv-010")]:
        events = []
        for i in range(count):
            events.append(
                {
                    "event_id": f"evt-priv-{doc}-{i:02d}",
                    "tenant_id": "tenant-a",
                    "actor_principal_id": f"p-priv-{i:03d}",
                    "object_id": doc,
                    "event_type": "view",
                    "source_system": "confluence",
                    "event_time": _iso(NOW - timedelta(minutes=i)),
                    "privacy_level": "public",
                }
            )
        cases.append(
            {
                "case_id": f"privacy-{count}",
                "document_id": doc,
                "tenant_id": "tenant-a",
                "distinct_actor_count": count,
                "privacy_threshold": threshold,
                "expect_privacy_protected": count < threshold,
                "events": events,
            }
        )
    return {
        "version": "v1",
        "privacy_threshold_default": threshold,
        "cases": cases,
    }


def build_retention_cases() -> dict:
    cases = []
    for i in range(5):
        cases.append(
            {
                "event_id": f"evt-ret-expired-{i:02d}",
                "tenant_id": "tenant-a",
                "actor_principal_id": f"p-user-{i+1:03d}",
                "object_id": "doc-ret-expired",
                "event_type": "view",
                "source_system": "slack",
                "event_time": _iso(NOW - timedelta(hours=2)),
                "privacy_level": "public",
                "ttl_seconds": 1,
                "ingested_at_offset_seconds": -3600,
                "expect_purged": True,
            }
        )
    for i in range(5):
        cases.append(
            {
                "event_id": f"evt-ret-active-{i:02d}",
                "tenant_id": "tenant-a",
                "actor_principal_id": f"p-user-{i+1:03d}",
                "object_id": "doc-ret-active",
                "event_type": "view",
                "source_system": "slack",
                "event_time": _iso(NOW - timedelta(minutes=i)),
                "privacy_level": "public",
                "ttl_seconds": 86400,
                "ingested_at_offset_seconds": 0,
                "expect_purged": False,
            }
        )
    for i in range(3):
        cases.append(
            {
                "event_id": f"evt-ret-hipriv-{i:02d}",
                "tenant_id": "tenant-a",
                "actor_principal_id": f"p-user-{i+1:03d}",
                "object_id": "doc-ret-hipriv",
                "event_type": "view",
                "source_system": "gdrive",
                "event_time": _iso(NOW - timedelta(hours=1)),
                "privacy_level": "confidential",
                "ttl_seconds": 2,
                "ingested_at_offset_seconds": -10,
                "expect_purged": True,
            }
        )
    return {
        "version": "v1",
        "description": "Retention cases use short TTLs so tests need not wait hours",
        "cases": cases,
    }


def build_ground_truth(events_doc: dict) -> dict:
    tenant = "tenant-a"
    events = [e for e in events_doc["events"] if e["tenant_id"] == tenant]
    popular_actors = {
        e["actor_principal_id"]
        for e in events
        if e["object_id"] == "doc-a-001" and e["event_type"] == "view"
    }
    alice = "p-user-001"
    alice_events = [e for e in events if e["actor_principal_id"] == alice]
    return {
        "version": "v1",
        "tenant_id": tenant,
        "documents": {
            "doc-a-001": {
                "min_distinct_viewers": 10,
                "expect_privacy_protected": False,
                "min_total_views": 10,
            }
        },
        "users": {
            alice: {
                "min_events": 1,
                "expect_last_active": True,
                "preferred_sources_includes_any": TENANTS[tenant]["sources"],
            }
        },
        "freshness": {
            "probe_event": {
                "event_id": "evt-freshness-probe",
                "tenant_id": tenant,
                "actor_principal_id": "p-user-001",
                "object_id": "doc-fresh-001",
                "event_type": "view",
                "source_system": "confluence",
                "event_time": _iso(NOW),
                "privacy_level": "public",
            },
            "seed_actors": [f"p-user-{i:03d}" for i in range(1, 7)],
            "max_freshness_seconds": 900,
        },
        "notes": {
            "alice_event_count": len(alice_events),
            "doc_a_001_distinct_viewers": len(popular_actors),
        },
    }


def main() -> None:
    events = build_events()
    privacy = build_privacy_cases()
    retention = build_retention_cases()
    truth = build_ground_truth(events)

    (OUT / "events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    (OUT / "privacy_test_cases.json").write_text(
        json.dumps(privacy, indent=2), encoding="utf-8"
    )
    (OUT / "retention_test_cases.json").write_text(
        json.dumps(retention, indent=2), encoding="utf-8"
    )
    (OUT / "signal_ground_truth.json").write_text(
        json.dumps(truth, indent=2), encoding="utf-8"
    )
    print(
        f"Wrote fixtures: events={len(events['events'])} "
        f"privacy_cases={len(privacy['cases'])} "
        f"retention_cases={len(retention['cases'])}"
    )


if __name__ == "__main__":
    main()
