"""Generate deterministic Block-Z-shaped fixtures for Block H signoff."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

TENANT = "tenant_h_test"
OUT = Path(__file__).resolve().parent

PEOPLE = [
    {"source_id": "person-alice", "display_name": "Alice Smith", "email": "alice@example.com", "title": "Staff Engineer", "department": "Engineering", "team": "Platform", "aliases": ["asmith"]},
    {"source_id": "person-bob", "display_name": "Bob Jones", "email": "bob@example.com", "title": "Senior Engineer", "department": "Engineering", "team": "Search", "aliases": ["bjones"]},
    {"source_id": "person-charlie", "display_name": "Charlie Brown", "email": "charlie@example.com", "title": "Engineer", "department": "Engineering", "team": "Platform", "aliases": []},
    {"source_id": "person-diana", "display_name": "Diana Prince", "email": "diana@example.com", "title": "PM", "department": "Product", "team": "Core", "aliases": ["wonder"]},
    {"source_id": "person-eve", "display_name": "Eve Anderson", "email": "eve@example.com", "title": "Designer", "department": "Product", "team": "Design", "aliases": []},
    {"source_id": "person-frank", "display_name": "Frank Miller", "email": "frank@example.com", "title": "Director", "department": "Engineering", "team": "Leadership", "aliases": ["fm"]},
    {"source_id": "person-grace", "display_name": "Grace Hopper", "email": "grace@example.com", "title": "Distinguished Engineer", "department": "Engineering", "team": "Platform", "aliases": ["ghopper"]},
    {"source_id": "person-henry", "display_name": "Henry Ford", "email": "henry@example.com", "title": "SRE", "department": "Engineering", "team": "Infra", "aliases": []},
    {"source_id": "person-isabel", "display_name": "Isabel Allende", "email": "isabel@example.com", "title": "Writer", "department": "Marketing", "team": "Content", "aliases": []},
    {"source_id": "person-jack", "display_name": "Jack London", "email": "jack@example.com", "title": "Support", "department": "Support", "team": "Tier2", "aliases": []},
    {"source_id": "person-alice-gmail", "display_name": "Alice Smith", "email": "alice@example.com", "title": "Staff Engineer", "department": "Engineering", "team": "Platform", "aliases": ["alice.smith"]},
]

GROUPS = [
    {"source_id": "group-eng", "display_name": "Engineering Team", "email": "eng@example.com"},
    {"source_id": "group-product", "display_name": "Product Team", "email": "product@example.com"},
    {"source_id": "group-allstaff", "display_name": "All Staff", "email": "allstaff@example.com"},
]

DOCS = [
    {"source_id": "doc-k8s-guide", "title": "Kubernetes Guide", "owner": "person-alice"},
    {"source_id": "doc-oauth-rfc", "title": "OAuth Internal RFC", "owner": "person-bob"},
    {"source_id": "doc-graph-design", "title": "Knowledge Graph Design", "owner": "person-grace"},
    {"source_id": "doc-acl-matrix", "title": "ACL Matrix", "owner": "person-frank"},
    {"source_id": "doc-onboarding", "title": "Eng Onboarding", "owner": "person-charlie"},
    {"source_id": "doc-roadmap", "title": "Product Roadmap", "owner": "person-diana"},
    {"source_id": "doc-incident-42", "title": "Incident 42 Postmortem", "owner": "person-henry"},
    {"source_id": "doc-brand-guide", "title": "Brand Guide", "owner": "person-isabel"},
    {"source_id": "ticket-search-latency", "title": "Search Latency Spike", "owner": "person-bob", "label": "Ticket"},
    {"source_id": "code-traverser", "title": "traverser.py", "owner": "person-grace", "label": "CodeFile"},
    {"source_id": "repo-sync-ai", "title": "sync-ai", "owner": "person-frank", "label": "Repository"},
]


def add_edge(edges, rel, src, tgt, **props):
    edges.append(
        {
            "source_id": src,
            "target_id": tgt,
            "relationship_type": rel,
            "properties": props,
        }
    )


def build_core_edges():
    edges = []
    add_edge(edges, "REPORTS_TO", "person-alice", "person-frank")
    add_edge(edges, "REPORTS_TO", "person-bob", "person-frank")
    add_edge(edges, "REPORTS_TO", "person-charlie", "person-alice")
    add_edge(edges, "REPORTS_TO", "person-grace", "person-frank")
    add_edge(edges, "REPORTS_TO", "person-henry", "person-frank")
    add_edge(edges, "REPORTS_TO", "person-diana", "person-eve")

    for pid in ["person-alice", "person-bob", "person-charlie", "person-grace", "person-henry"]:
        add_edge(edges, "BELONGS_TO", pid, "group-eng")
    for pid in ["person-diana", "person-eve"]:
        add_edge(edges, "BELONGS_TO", pid, "group-product")
    add_edge(edges, "BELONGS_TO", "person-frank", "group-allstaff")

    add_edge(edges, "MEMBER_OF", "group-eng", "group-allstaff")
    add_edge(edges, "MEMBER_OF", "group-product", "group-allstaff")

    for doc in DOCS:
        add_edge(edges, "AUTHORED", doc["owner"], doc["source_id"])
        add_edge(edges, "OWNS", doc["source_id"], doc["owner"])

    add_edge(edges, "VIEWED", "person-bob", "doc-k8s-guide")
    add_edge(edges, "VIEWED", "person-charlie", "doc-k8s-guide")
    add_edge(edges, "VIEWED", "person-diana", "doc-roadmap")
    add_edge(edges, "VIEWED", "person-alice", "doc-graph-design")
    add_edge(edges, "VIEWED", "person-henry", "doc-incident-42")
    add_edge(edges, "COMMENTED_ON", "person-bob", "doc-graph-design")
    add_edge(edges, "COMMENTED_ON", "person-grace", "doc-oauth-rfc")
    add_edge(edges, "COMMENTED_ON", "person-frank", "doc-acl-matrix")

    add_edge(edges, "SHARED_WITH", "person-alice", "person-bob")
    add_edge(edges, "SHARED_WITH", "person-alice", "group-eng")
    add_edge(edges, "SHARED_WITH", "person-diana", "group-product")
    add_edge(edges, "SHARED_WITH", "person-frank", "person-grace")

    add_edge(edges, "REFERENCES", "doc-graph-design", "doc-oauth-rfc")
    add_edge(edges, "REFERENCES", "doc-graph-design", "code-traverser")
    add_edge(edges, "REFERENCES", "doc-incident-42", "doc-k8s-guide")
    add_edge(edges, "LINKED_TO", "doc-onboarding", "doc-k8s-guide")
    add_edge(edges, "LINKED_TO", "doc-roadmap", "doc-oauth-rfc")
    add_edge(edges, "LINKED_TO", "doc-acl-matrix", "doc-graph-design")

    add_edge(edges, "WORKED_ON", "person-bob", "ticket-search-latency")
    add_edge(edges, "WORKED_ON", "person-alice", "ticket-search-latency")
    add_edge(edges, "WORKED_ON", "person-grace", "code-traverser")
    add_edge(edges, "WORKED_ON", "person-henry", "code-traverser")

    add_edge(edges, "AUTHORED", "person-alice-gmail", "doc-brand-guide")
    add_edge(edges, "VIEWED", "person-alice-gmail", "doc-onboarding")
    add_edge(edges, "BELONGS_TO", "person-alice-gmail", "group-eng")
    add_edge(edges, "COMMENTED_ON", "person-alice-gmail", "doc-k8s-guide")
    return edges


def pad_for_latency(people, docs, edges):
    """Ensure >= 50 nodes for H2 (50 distinct start nodes)."""
    for i in range(1, 31):
        pid = f"person-extra-{i:02d}"
        did = f"doc-extra-{i:02d}"
        people.append(
            {
                "source_id": pid,
                "display_name": f"Extra User {i}",
                "email": f"extra{i}@example.com",
                "title": "IC",
                "department": "Engineering" if i % 2 == 0 else "Product",
                "team": f"Team-{i % 5}",
                "aliases": [],
            }
        )
        docs.append({"source_id": did, "title": f"Extra Doc {i}", "owner": pid})
        add_edge(edges, "AUTHORED", pid, did)
        add_edge(edges, "OWNS", did, pid)
        if i > 1:
            add_edge(edges, "REPORTS_TO", pid, f"person-extra-{i - 1:02d}")
        add_edge(
            edges,
            "BELONGS_TO",
            pid,
            "group-eng" if i % 2 == 0 else "group-product",
        )


def main() -> None:
    people = list(PEOPLE)
    docs = list(DOCS)
    edges = build_core_edges()
    pad_for_latency(people, docs, edges)

    counts = Counter(e["relationship_type"] for e in edges)
    graph_edges = {
        "version": "1.0",
        "fixture_provenance": (
            "block-h-local (Block Z shared package absent; schema matches master prompt)"
        ),
        "tenant_id": TENANT,
        "edges": edges,
        "expected_counts": dict(sorted(counts.items())),
        "total_edges": len(edges),
        "merge_candidates": {
            "primary_id": "person-alice",
            "secondary_id": "person-alice-gmail",
        },
    }
    (OUT / "graph_edges.json").write_text(
        json.dumps(graph_edges, indent=2) + "\n", encoding="utf-8"
    )

    principals = {
        "version": "1.0",
        "tenant_id": TENANT,
        "people": people,
        "groups": GROUPS,
    }
    (OUT / "principals.json").write_text(
        json.dumps(principals, indent=2) + "\n", encoding="utf-8"
    )

    documents = {"version": "1.0", "tenant_id": TENANT, "documents": docs}
    (OUT / "documents.json").write_text(
        json.dumps(documents, indent=2) + "\n", encoding="utf-8"
    )

    events = []
    for p in people:
        events.append(
            {
                "tenant_id": TENANT,
                "event_type": "PrincipalCreated",
                "payload": {
                    "principal_id": p["source_id"],
                    **{k: v for k, v in p.items() if k != "source_id"},
                },
            }
        )
    for g in GROUPS:
        events.append(
            {
                "tenant_id": TENANT,
                "event_type": "GroupCreated",
                "payload": {
                    "group_id": g["source_id"],
                    "name": g["display_name"],
                    "email": g.get("email"),
                },
            }
        )
    for d in docs:
        events.append(
            {
                "tenant_id": TENANT,
                "event_type": "DocumentCreated",
                "payload": {
                    "document_id": d["source_id"],
                    "title": d["title"],
                    "owner_principal_id": d["owner"],
                    "object_type": d.get("label", "Document").lower(),
                },
            }
        )
    for e in edges:
        et = e["relationship_type"]
        if et == "VIEWED":
            events.append(
                {
                    "tenant_id": TENANT,
                    "event_type": "ActivityViewed",
                    "payload": {
                        "principal_id": e["source_id"],
                        "document_id": e["target_id"],
                    },
                }
            )
        elif et == "COMMENTED_ON":
            events.append(
                {
                    "tenant_id": TENANT,
                    "event_type": "ActivityCommented",
                    "payload": {
                        "principal_id": e["source_id"],
                        "document_id": e["target_id"],
                    },
                }
            )

    (OUT / "canonical_events.json").write_text(
        json.dumps({"version": "1.0", "tenant_id": TENANT, "events": events}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    acl = {
        "version": "1.0",
        "fixture_provenance": "block-h-local",
        "cases": [
            {
                "case_id": "acl-h-01-cross-tenant",
                "description": "Cross-tenant graph access must fail binding",
                "tenant_id": TENANT,
                "forbidden_tenant_id": "tenant_other",
                "node_id": "doc-acl-matrix",
            }
        ],
    }
    (OUT / "acl_redteam_cases.json").write_text(
        json.dumps(acl, indent=2) + "\n", encoding="utf-8"
    )

    node_count = len(people) + len(GROUPS) + len(docs)
    print(f"Wrote fixtures to {OUT}")
    print(f"Nodes={node_count} edges={len(edges)}")
    print("Counts:", dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
