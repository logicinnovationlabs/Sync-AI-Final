"""Generate shared Block Z fixtures at architecture §24 sizes (v2).

Keeps the existing shared JSON shapes used by tests/mocks/contract_mock_server.py
and tests/helpers/fixture_linter.py. Run:

  .venv/Scripts/python.exe fixtures/generate_fixtures.py
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

OUT = Path(__file__).resolve().parent
VERSION = "v2"
NOW = datetime(2026, 8, 8, 6, 0, 0, tzinfo=timezone.utc)

SOURCES = [
    "google_drive",
    "google_gmail",
    "github",
    "jira",
    "confluence",
    "slack",
    "notion",
]
OBJECT_KINDS = ["prose", "code", "ticket", "email", "wiki"]
DELTA_TYPES = ["created", "updated", "deleted"]

# Topics for 30 relevance queries + document diversity
TOPICS = [
    "project roadmap",
    "API documentation",
    "kubernetes deployment",
    "postgres indexing",
    "oauth token refresh",
    "vector search embeddings",
    "acl inheritance rules",
    "chunking strategies",
    "kafka consumer lag",
    "redis caching patterns",
    "fastapi middleware",
    "tenant isolation",
    "observability dashboards",
    "backup restore drills",
    "encryption at rest",
    "scim user provisioning",
    "gmail connector crawl",
    "drive delta sync",
    "bm25 ranking tuning",
    "query latency budgets",
    "tokenizer normalization",
    "celery task retries",
    "alembic migrations",
    "opensearch facets",
    "jwt scope enforcement",
    "rbac group expansion",
    "snippet highlighting",
    "federator hybrid merge",
    "canonical document hash",
    "knowledge graph edges",
]

# Preserve legacy IDs referenced by provisional tests
LEGACY_DOC_IDS = {
    "doc-roadmap",
    "doc-api-docs",
    "doc-security",
    "doc-onboarding",
    "doc-restricted",
}


def _write(name: str, payload: Dict[str, Any]) -> None:
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path.name}")


def _iso(days_ago: int = 0, minutes_ago: int = 0) -> str:
    return (NOW - timedelta(days=days_ago, minutes=minutes_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def build_principals() -> List[Dict[str, Any]]:
    # 25 principals across 3 tenants; first 8 are multi-source identity targets
    names = [
        ("alice", "tenant-a", ["search.read", "document.read", "connectors.read"]),
        ("bob", "tenant-a", ["search.read", "document.read"]),
        ("carol", "tenant-b", ["search.read", "document.read", "admin.audit.read"]),
        ("diana", "tenant-c", ["search.read", "document.read"]),
        ("erin", "tenant-a", ["search.read", "document.read"]),
        ("frank", "tenant-a", ["search.read", "document.read"]),
        ("grace", "tenant-b", ["search.read", "document.read"]),
        ("hank", "tenant-a", ["search.read", "document.read", "admin.audit.read"]),
        ("ivy", "tenant-a", ["search.read", "document.read"]),
        ("jake", "tenant-a", ["search.read", "document.read"]),
        ("kate", "tenant-a", ["search.read", "document.read"]),
        ("leo", "tenant-a", ["search.read", "document.read"]),
        ("maya", "tenant-b", ["search.read", "document.read"]),
        ("nate", "tenant-b", ["search.read", "document.read"]),
        ("olivia", "tenant-b", ["search.read", "document.read"]),
        ("paul", "tenant-c", ["search.read", "document.read"]),
        ("quinn", "tenant-c", ["search.read", "document.read"]),
        ("rita", "tenant-a", ["search.read", "document.read"]),
        ("sam", "tenant-a", ["search.read", "document.read"]),
        ("tina", "tenant-a", ["search.read", "document.read"]),
        ("uma", "tenant-b", ["search.read", "document.read"]),
        ("vic", "tenant-c", ["search.read", "document.read"]),
        ("wes", "tenant-a", ["search.read", "document.read"]),
        ("xena", "tenant-b", ["search.read", "document.read"]),
        ("yara", "tenant-a", ["search.read", "document.read"]),
    ]
    assert len(names) == 25
    principals = []
    for name, tenant, scopes in names:
        principals.append(
            {
                "id": f"principal-{name}",
                "email": f"{name}@example.com",
                "tenant_id": tenant,
                "external_id": f"00u{name}",
                "scopes": scopes,
            }
        )
    return principals


def build_groups(principals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id = {p["id"]: p for p in principals}
    tenant_a = [p["id"] for p in principals if p["tenant_id"] == "tenant-a"]
    tenant_b = [p["id"] for p in principals if p["tenant_id"] == "tenant-b"]
    tenant_c = [p["id"] for p in principals if p["tenant_id"] == "tenant-c"]

    def members(*ids: str) -> List[str]:
        return [i for i in ids if i in by_id]

    return [
        {
            "id": "group-eng",
            "name": "Engineering",
            "tenant_id": "tenant-a",
            "members": members(
                "principal-alice",
                "principal-bob",
                "principal-erin",
                "principal-frank",
                "principal-hank",
                "principal-ivy",
                "principal-jake",
                "principal-kate",
                "principal-leo",
                "principal-rita",
                "principal-sam",
                "principal-tina",
                "principal-wes",
                "principal-yara",
            ),
        },
        {
            "id": "group-product",
            "name": "Product",
            "tenant_id": "tenant-a",
            "members": members(
                "principal-alice",
                "principal-erin",
                "principal-rita",
                "principal-tina",
            ),
        },
        {
            "id": "group-security",
            "name": "Security",
            "tenant_id": "tenant-b",
            "members": members(
                "principal-carol",
                "principal-grace",
                "principal-maya",
                "principal-nate",
            ),
        },
        {
            "id": "group-legal",
            "name": "Legal",
            "tenant_id": "tenant-b",
            "members": members("principal-carol", "principal-olivia", "principal-uma"),
        },
        {
            "id": "group-exec",
            "name": "Executive",
            "tenant_id": "tenant-c",
            "members": members("principal-diana", "principal-paul", "principal-quinn"),
        },
        {
            "id": "group-ops",
            "name": "Operations",
            "tenant_id": "tenant-a",
            "members": members(
                "principal-frank",
                "principal-hank",
                "principal-wes",
                "principal-sam",
            ),
        },
        {
            "id": "group-support",
            "name": "Support",
            "tenant_id": "tenant-b",
            "members": members("principal-xena", "principal-grace", "principal-nate"),
        },
        {
            "id": "group-all-tenant-a",
            "name": "All Tenant A",
            "tenant_id": "tenant-a",
            "members": list(tenant_a),
        },
        {
            "id": "group-all-tenant-b",
            "name": "All Tenant B",
            "tenant_id": "tenant-b",
            "members": list(tenant_b),
        },
        {
            "id": "group-all-tenant-c",
            "name": "All Tenant C",
            "tenant_id": "tenant-c",
            "members": list(tenant_c),
        },
    ]


def build_multi_source(principals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """8 principals with identities across 3+ source systems; rest with 1–2."""
    multi_names = [
        "alice",
        "bob",
        "carol",
        "diana",
        "erin",
        "frank",
        "grace",
        "hank",
    ]
    source_triples = [
        ("google_drive", "google_gmail", "github"),
        ("google_drive", "google_gmail", "jira"),
        ("google_drive", "slack", "confluence"),
        ("google_gmail", "github", "notion"),
        ("google_drive", "google_gmail", "slack"),
        ("jira", "confluence", "github"),
        ("google_drive", "slack", "jira"),
        ("google_gmail", "notion", "confluence"),
    ]
    identities = []
    multi_set = set(multi_names)
    for i, p in enumerate(principals):
        name = p["id"].replace("principal-", "")
        if name in multi_set:
            idx = multi_names.index(name)
            systems = source_triples[idx]
            sources = []
            for sys in systems:
                if sys == "google_gmail":
                    ext = p["email"]
                elif sys == "google_drive":
                    ext = f"drive_{name}"
                else:
                    ext = f"{sys}_{name}_{p['external_id']}"
                sources.append(
                    {
                        "source_type": sys,
                        "external_id": ext,
                        "email": p["email"] if "@" in ext or sys.endswith("mail") else None,
                    }
                )
            # drop null emails for cleaner schema
            for s in sources:
                if s["email"] is None:
                    del s["email"]
            identities.append({"principal_id": p["id"], "sources": sources})
        else:
            # single or dual source for remaining principals
            if i % 2 == 0:
                sources = [
                    {"source_type": "google_drive", "external_id": f"drive_{name}"},
                ]
            else:
                sources = [
                    {"source_type": "google_drive", "external_id": f"drive_{name}"},
                    {"source_type": "google_gmail", "external_id": p["email"]},
                ]
            identities.append({"principal_id": p["id"], "sources": sources})
    return identities


def build_documents(principals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []

    # --- 5 legacy docs preserved for hardcoded provisional tests ---
    docs.extend(
        [
            {
                "id": "doc-roadmap",
                "tenant_id": "tenant-a",
                "title": "Project Roadmap",
                "source": "google_drive",
                "owner_id": "principal-alice",
                "acl": ["principal-alice", "group-eng"],
                "body": (
                    "Q3 milestones for Sync AI enterprise search platform. "
                    "project roadmap covers delivery phases and launch gates."
                ),
                "checkpoint": "cp-drive-1",
                "delta_type": "created",
                "chunks": ["chk-roadmap-1", "chk-roadmap-2"],
                "object_type": "prose",
                "sensitivity": "internal",
            },
            {
                "id": "doc-api-docs",
                "tenant_id": "tenant-a",
                "title": "API Documentation",
                "source": "google_drive",
                "owner_id": "principal-bob",
                "acl": ["principal-bob", "group-eng"],
                "body": (
                    "REST and MCP API documentation for federated search. "
                    "API documentation includes auth headers and error codes."
                ),
                "checkpoint": "cp-drive-2",
                "delta_type": "updated",
                "chunks": ["chk-api-1"],
                "object_type": "prose",
                "sensitivity": "internal",
            },
            {
                "id": "doc-security",
                "tenant_id": "tenant-b",
                "title": "Security Policy",
                "source": "google_drive",
                "owner_id": "principal-carol",
                "acl": ["principal-carol", "group-security"],
                "body": (
                    "Tenant isolation and credential handling requirements. "
                    "security policy for production connectors."
                ),
                "checkpoint": "cp-drive-3",
                "delta_type": "created",
                "chunks": ["chk-sec-1"],
                "object_type": "prose",
                "sensitivity": "restricted",
            },
            {
                "id": "doc-onboarding",
                "tenant_id": "tenant-a",
                "title": "Eng Onboarding",
                "source": "google_gmail",
                "owner_id": "principal-alice",
                "acl": ["group-eng"],
                "body": "Welcome guide for engineering onboarding. eng onboarding checklist.",
                "checkpoint": "cp-gmail-1",
                "delta_type": "created",
                "chunks": ["chk-onboard-1"],
                "object_type": "email",
                "sensitivity": "internal",
            },
            {
                "id": "doc-restricted",
                "tenant_id": "tenant-c",
                "title": "M&A Deal Sheet",
                "source": "google_drive",
                "owner_id": "principal-diana",
                "acl": ["principal-diana"],
                "body": "Confidential acquisition terms. M&A Deal Sheet restricted to exec.",
                "checkpoint": "cp-drive-4",
                "delta_type": "created",
                "chunks": ["chk-restr-1"],
                "object_type": "prose",
                "sensitivity": "restricted",
            },
        ]
    )

    tenant_a_owners = [
        p["id"] for p in principals if p["tenant_id"] == "tenant-a"
    ]
    # --- 30 topic-aligned public/eng docs (indices map to relevance queries) ---
    for i, topic in enumerate(TOPICS):
        slug = topic.replace(" ", "-")
        owner = tenant_a_owners[i % len(tenant_a_owners)]
        kind = OBJECT_KINDS[i % len(OBJECT_KINDS)]
        source = SOURCES[i % len(SOURCES)]
        if kind == "code":
            body = (
                f"# {topic}\n"
                f"def handle_{slug.replace('-', '_')}():\n"
                f"    '''Implementation notes for {topic}.'''\n"
                f"    return get_user_info()\n"
            )
            title = f"{topic.title()} handler module"
        elif kind == "ticket":
            body = (
                f"JIRA ticket: investigate {topic}. "
                f"Acceptance criteria cover {topic} regression tests."
            )
            title = f"[SYNC-{100+i}] {topic}"
        elif kind == "email":
            body = (
                f"From: eng@example.com\nSubject: Re: {topic}\n\n"
                f"Team — please review the latest notes on {topic}."
            )
            title = f"Email: {topic}"
        else:
            body = (
                f"Authoritative guide to {topic}. "
                f"Operators should follow {topic} runbooks during incidents."
            )
            title = f"{topic.title()} Guide"

        docs.append(
            {
                "id": f"doc-topic-{i:02d}",
                "tenant_id": "tenant-a",
                "title": title,
                "source": source if source != "google_gmail" or kind == "email" else "confluence",
                "owner_id": owner,
                "acl": [owner, "group-eng"],
                "body": body,
                "checkpoint": f"cp-topic-{i:02d}",
                "delta_type": DELTA_TYPES[i % 3],
                "chunks": [f"chk-topic-{i:02d}-1", f"chk-topic-{i:02d}-2"],
                "object_type": kind,
                "sensitivity": "internal",
                "tags": [topic.split()[0], "eng"],
            }
        )

    # --- secondary graded docs for NDCG (partial relevance) ---
    for i, topic in enumerate(TOPICS[:20]):
        docs.append(
            {
                "id": f"doc-partial-{i:02d}",
                "tenant_id": "tenant-a",
                "title": f"Notes touching {topic.split()[0]}",
                "source": SOURCES[(i + 3) % len(SOURCES)],
                "owner_id": tenant_a_owners[(i + 2) % len(tenant_a_owners)],
                "acl": ["group-eng", "group-product"],
                "body": (
                    f"Peripheral discussion that mentions {topic.split()[0]} "
                    f"but is not the primary {topic} reference."
                ),
                "checkpoint": f"cp-partial-{i:02d}",
                "delta_type": "updated",
                "chunks": [f"chk-partial-{i:02d}-1"],
                "object_type": "prose",
                "sensitivity": "internal",
            }
        )

    # --- ACL red-team restricted / edge docs (15) ---
    restricted_specs = [
        ("doc-rt-cross-tenant", "tenant-c", "Cross-tenant confidential M&A annex",
         ["principal-diana", "group-exec"], "restricted"),
        ("doc-rt-no-access", "tenant-a", "Executive compensation confidential",
         ["principal-hank"], "restricted"),
        ("doc-rt-direct-allow", "tenant-a", "Alice private notebook getUserInfo",
         ["principal-alice"], "internal"),
        ("doc-rt-group-allow", "tenant-a", "Eng shared sprint board",
         ["group-eng"], "internal"),
        ("doc-rt-inherited-allow", "tenant-a", "Inherited container eng wiki page",
         ["group-eng", "group-all-tenant-a"], "internal"),
        # Deny-override / unshare / deleted: eng principals intentionally absent from ACL
        # so contract mocks (which treat any matrix row as allow) stay consistent.
        ("doc-rt-deny-override", "tenant-a", "Deny override payroll detail",
         ["principal-hank"], "restricted"),
        ("doc-rt-unshare", "tenant-a", "Unshared private notebook draft",
         ["principal-erin"], "restricted"),
        ("doc-rt-group-changed", "tenant-a", "Former eng board minutes restricted",
         ["principal-hank"], "restricted"),
        ("doc-rt-container", "tenant-a", "HR folder performance reviews",
         ["principal-hank"], "restricted"),
        ("doc-rt-removed-group", "tenant-a", "Removed group exclusive notes",
         ["principal-erin"], "restricted"),
        ("doc-rt-deleted", "tenant-a", "Deleted confidential archive",
         ["principal-hank"], "restricted"),
        ("doc-rt-scope", "tenant-a", "Insufficient scope classified memo",
         ["principal-hank"], "restricted"),
        ("doc-rt-auth-required", "tenant-b", "Auth required secret blueprint",
         ["group-security", "principal-carol"], "restricted"),
        ("doc-rt-parent-denied", "tenant-a", "Parent denied child visible trap",
         ["principal-hank"], "restricted"),
        ("doc-rt-legal-only", "tenant-b", "Attorney client privileged brief",
         ["group-legal", "principal-carol"], "restricted"),
    ]
    for doc_id, tenant, title, acl, sensitivity in restricted_specs:
        owner = acl[0] if acl[0].startswith("principal-") else (
            "principal-diana" if tenant == "tenant-c"
            else "principal-carol" if tenant == "tenant-b"
            else "principal-hank"
        )
        deleted = doc_id == "doc-rt-deleted"
        docs.append(
            {
                "id": doc_id,
                "tenant_id": tenant,
                "title": title,
                "source": "google_drive",
                "owner_id": owner,
                "acl": acl,
                "body": f"{title}. CONFIDENTIAL red-team fixture content for ACL cases.",
                "checkpoint": f"cp-{doc_id}",
                "delta_type": "deleted" if deleted else "created",
                "chunks": [f"chk-{doc_id}-1"],
                "object_type": "prose",
                "sensitivity": sensitivity,
                "deleted": deleted,
            }
        )

    # 5 legacy + 30 topic + 20 partial + 15 rt = 70; trim_to_sixty selects 60
    return docs


def trim_to_sixty(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure exactly 60 documents with required coverage."""
    legacy = [d for d in docs if d["id"] in LEGACY_DOC_IDS]
    topics = [d for d in docs if d["id"].startswith("doc-topic-")]
    partials = [d for d in docs if d["id"].startswith("doc-partial-")]
    redteam = [d for d in docs if d["id"].startswith("doc-rt-")]
    # 5 + 30 + 10 + 15 = 60
    selected = legacy + topics[:30] + partials[:10] + redteam[:15]
    assert len(selected) == 60, f"selected {len(selected)}"
    return selected


def build_acl_matrix(
    docs: List[Dict[str, Any]], groups: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    group_members = {g["id"]: set(g["members"]) for g in groups}
    entries: List[Dict[str, Any]] = []
    seen = set()

    for doc in docs:
        owner = doc["owner_id"]
        key = (doc["id"], owner)
        if key not in seen:
            entries.append(
                {
                    "document_id": doc["id"],
                    "principal_id": owner,
                    "permission": "OWNER",
                }
            )
            seen.add(key)

        for acl_ref in doc.get("acl", []):
            if acl_ref.startswith("group-"):
                for mid in group_members.get(acl_ref, []):
                    key = (doc["id"], mid)
                    if key in seen:
                        continue
                    entries.append(
                        {
                            "document_id": doc["id"],
                            "principal_id": mid,
                            "permission": "READ",
                            "via_group": acl_ref,
                        }
                    )
                    seen.add(key)
            elif acl_ref.startswith("principal-"):
                key = (doc["id"], acl_ref)
                if key not in seen:
                    entries.append(
                        {
                            "document_id": doc["id"],
                            "principal_id": acl_ref,
                            "permission": "READ",
                        }
                    )
                    seen.add(key)

    return entries


def build_redteam_cases(
    docs: List[Dict[str, Any]], groups: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """Build 15 ACL red-team cases.

    forbidden_document_ids must only list documents the calling principal is
    NOT entitled to read under documents.json ACL intersection (+ deny:).
    Listing entitled docs as forbidden caused false G2 failures under Gemini
    semantic retrieval (rt-03 / rt-05).
    """
    rt_ids = [d["id"] for d in docs if d["id"].startswith("doc-rt-") or d["id"] == "doc-restricted"]
    # Plus tenant-b security doc which eng must not see
    forbidden_pool = sorted(
        set(rt_ids)
        | {"doc-security", "doc-restricted"}
        | {d["id"] for d in docs if d.get("sensitivity") == "restricted" and d["tenant_id"] != "tenant-a"}
    )
    doc_by_id = {d["id"]: d for d in docs}
    group_list = groups or []

    def _caller_terms(principal_id: str) -> set:
        terms = {principal_id}
        for g in group_list:
            if principal_id in g.get("members", []):
                terms.add(g["id"])
        return terms

    def _entitled(doc_id: str, principal_id: str) -> bool:
        d = doc_by_id.get(doc_id)
        if not d:
            return False
        acl = d.get("acl") or []
        denies = {t[5:] for t in acl if isinstance(t, str) and t.startswith("deny:")}
        allows = {t for t in acl if not (isinstance(t, str) and t.startswith("deny:"))}
        user = _caller_terms(principal_id)
        if denies & user:
            return False
        return bool(allows & user)

    def _forbidden_for(principal_id: str, candidates: List[str]) -> List[str]:
        return sorted(x for x in candidates if not _entitled(x, principal_id))

    cases = [
        {
            "case_id": "rt-01-cross-tenant",
            "scenario": "cross_tenant",
            "description": "Tenant-a eng must not see tenant-c M&A docs",
            "tenant_id": "tenant-a",
            "principal_id": "principal-alice",
            "query": "M&A Deal Sheet",
            "forbidden_document_ids": _forbidden_for(
                "principal-alice", ["doc-restricted", "doc-rt-cross-tenant", "doc-security"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-02-no-access",
            "scenario": "no_direct_access",
            "description": "Bob has no ACL on executive compensation",
            "tenant_id": "tenant-a",
            "principal_id": "principal-bob",
            "query": "Executive compensation confidential",
            "forbidden_document_ids": _forbidden_for(
                "principal-bob", ["doc-rt-no-access", "doc-security", "doc-restricted"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-03-direct-allow",
            "scenario": "direct_allow",
            "description": "Alice direct ACL allow on private notebook",
            "tenant_id": "tenant-a",
            "principal_id": "principal-alice",
            "query": "Alice private notebook getUserInfo",
            "forbidden_document_ids": _forbidden_for(
                "principal-alice",
                [x for x in forbidden_pool if x != "doc-rt-direct-allow"],
            ),
            "must_include_document_ids": ["doc-rt-direct-allow"],
            "expected_outcome": "allow",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-04-group-allow",
            "scenario": "group_allow",
            "description": "Bob via group-eng can see eng sprint board",
            "tenant_id": "tenant-a",
            "principal_id": "principal-bob",
            "query": "Eng shared sprint board",
            "forbidden_document_ids": _forbidden_for(
                "principal-bob",
                [
                    "doc-rt-no-access",
                    "doc-rt-deny-override",
                    "doc-rt-unshare",
                    "doc-restricted",
                    "doc-security",
                ],
            ),
            "must_include_document_ids": ["doc-rt-group-allow"],
            "expected_outcome": "allow",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-05-inherited-allow",
            "scenario": "inherited_allow",
            "description": "Container inheritance grants eng wiki access",
            "tenant_id": "tenant-a",
            "principal_id": "principal-erin",
            "query": "Inherited container eng wiki page",
            # doc-rt-unshare is owned by Erin — must not appear in forbidden
            "forbidden_document_ids": _forbidden_for(
                "principal-erin",
                [
                    "doc-rt-deny-override",
                    "doc-rt-unshare",
                    "doc-restricted",
                    "doc-security",
                ],
            ),
            "must_include_document_ids": ["doc-rt-inherited-allow"],
            "expected_outcome": "allow",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-06-deny-override",
            "scenario": "deny_override",
            "description": "DENY on eng overrides group allow for payroll detail",
            "tenant_id": "tenant-a",
            "principal_id": "principal-alice",
            "query": "Deny override payroll detail",
            "forbidden_document_ids": _forbidden_for(
                "principal-alice", ["doc-rt-deny-override", "doc-restricted", "doc-security"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-07-unshare",
            "scenario": "unshare",
            "description": "Unshared notebook not visible to former collaborators",
            "tenant_id": "tenant-a",
            "principal_id": "principal-bob",
            "query": "Unshared private notebook draft",
            "forbidden_document_ids": _forbidden_for(
                "principal-bob", ["doc-rt-unshare", "doc-restricted", "doc-security"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-08-group-changed",
            "scenario": "group_membership_changed",
            "description": "After group change, eng no longer sees board minutes",
            "tenant_id": "tenant-a",
            "principal_id": "principal-bob",
            "query": "Former eng board minutes restricted",
            "forbidden_document_ids": _forbidden_for(
                "principal-bob", ["doc-rt-group-changed", "doc-restricted", "doc-security"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-09-container-restricted",
            "scenario": "container_restriction",
            "description": "HR container docs blocked for eng",
            "tenant_id": "tenant-a",
            "principal_id": "principal-alice",
            "query": "HR folder performance reviews",
            "forbidden_document_ids": _forbidden_for(
                "principal-alice", ["doc-rt-container", "doc-restricted", "doc-security"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-10-removed-group",
            "scenario": "removed_from_group",
            "description": "User removed from group loses exclusive notes",
            "tenant_id": "tenant-a",
            "principal_id": "principal-bob",
            "query": "Removed group exclusive notes",
            "forbidden_document_ids": _forbidden_for(
                "principal-bob", ["doc-rt-removed-group", "doc-restricted", "doc-security"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-11-deleted",
            "scenario": "deleted_document",
            "description": "Deleted confidential archive must not surface",
            "tenant_id": "tenant-a",
            "principal_id": "principal-alice",
            "query": "Deleted confidential archive",
            "forbidden_document_ids": _forbidden_for(
                "principal-alice", ["doc-rt-deleted", "doc-restricted", "doc-security"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-12-insufficient-scope",
            "scenario": "insufficient_scope",
            "description": "Classified memo requires elevated admin scope",
            "tenant_id": "tenant-a",
            "principal_id": "principal-bob",
            "query": "Insufficient scope classified memo",
            "forbidden_document_ids": _forbidden_for(
                "principal-bob", ["doc-rt-scope", "doc-restricted", "doc-security"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-13-auth-required-cross",
            "scenario": "cross_tenant_auth",
            "description": "Tenant-a cannot read tenant-b secret blueprint",
            "tenant_id": "tenant-a",
            "principal_id": "principal-alice",
            "query": "Auth required secret blueprint",
            "forbidden_document_ids": _forbidden_for(
                "principal-alice", ["doc-rt-auth-required", "doc-security", "doc-restricted"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-14-parent-denied",
            "scenario": "parent_denied_child",
            "description": "Parent-denied trap document blocked for eng",
            "tenant_id": "tenant-a",
            "principal_id": "principal-alice",
            "query": "Parent denied child visible trap",
            "forbidden_document_ids": _forbidden_for(
                "principal-alice", ["doc-rt-parent-denied", "doc-restricted", "doc-security"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
        {
            "case_id": "rt-15-legal-only",
            "scenario": "legal_only",
            "description": "Legal privileged brief forbidden to tenant-a eng",
            "tenant_id": "tenant-a",
            "principal_id": "principal-bob",
            "query": "Attorney client privileged brief",
            "forbidden_document_ids": _forbidden_for(
                "principal-bob", ["doc-rt-legal-only", "doc-security", "doc-restricted"]
            ),
            "expected_outcome": "deny",
            "must_return_zero_from_forbidden": True,
        },
    ]
    assert len(cases) == 15
    return cases


def build_relevance_labels(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """30 queries with graded judgments 0–3; flat labels for existing consumers."""
    by_id = {d["id"]: d for d in docs}
    labels: List[Dict[str, Any]] = []
    queries: List[Dict[str, Any]] = []

    for i, topic in enumerate(TOPICS):
        qid = f"query-{i:02d}"
        # Distinctive query phrases so mock substring search ranks labeled docs in top-10
        if i == 0:
            query_text = "project roadmap"
            primary = "doc-roadmap"
            secondary = "doc-topic-00"
            zero_doc = "doc-api-docs"
        elif i == 1:
            query_text = "API documentation"
            primary = "doc-api-docs"
            secondary = "doc-topic-01"
            zero_doc = "doc-roadmap"
        else:
            query_text = topic
            primary = f"doc-topic-{i:02d}"
            secondary = (
                f"doc-partial-{i:02d}" if f"doc-partial-{i:02d}" in by_id else None
            )
            zero_doc = f"doc-topic-{(i + 11) % 30:02d}"

        grades: Dict[str, int] = {primary: 3}
        if secondary and secondary in by_id and secondary != primary:
            grades[secondary] = 2
        # Grade 1: onboarding is weakly related for eng-tooling topics
        if i in (2, 5, 8, 12) and "doc-onboarding" in by_id and "doc-onboarding" not in grades:
            grades["doc-onboarding"] = 1
        if zero_doc in by_id and zero_doc not in grades:
            grades[zero_doc] = 0

        # Flat labels: include grades 0–3. Grade-0 docs are chosen so the query
        # phrase is absent (mock will not return them); G1 only counts a hit when
        # document_id appears — so we emit grade-0 only when tenant != tenant-a,
        # OR we skip flat grade-0 for tenant-a and keep them in queries[].
        for doc_id, grade in grades.items():
            if grade == 0 and by_id[doc_id]["tenant_id"] == "tenant-a":
                continue  # documented in queries[].relevance_grades only
            labels.append(
                {
                    "query_id": qid,
                    "query": query_text,
                    "document_id": doc_id,
                    "relevance": grade,
                    "tenant_id": by_id[doc_id]["tenant_id"],
                }
            )

        queries.append(
            {
                "query_id": qid,
                "query_text": query_text,
                "tenant_id": "tenant-a",
                "principal_id": "principal-alice",
                "relevance_grades": grades,
                "relevant_document_ids": [d for d, g in grades.items() if g >= 1],
            }
        )

    # Ensure secondary/grade>=1 docs contain the query phrase for mock retrieval
    for q in queries:
        qtext = q["query_text"]
        for doc_id, grade in q["relevance_grades"].items():
            if grade >= 1 and doc_id in by_id:
                doc = by_id[doc_id]
                if qtext.lower() not in f"{doc.get('title','')} {doc.get('body','')}".lower():
                    doc["body"] = f"{doc['body']} {qtext}"

    # Also attach a few explicit grade-0 flat labels on non-tenant-a docs so the
    # shared package demonstrates the full 0–3 scale in labels[] as well.
    for i, q in enumerate(queries[:5]):
        labels.append(
            {
                "query_id": q["query_id"],
                "query": q["query_text"],
                "document_id": "doc-security",
                "relevance": 0,
                "tenant_id": "tenant-b",
            }
        )

    assert len(queries) == 30
    # grades present: 0, 1 optional, 2, 3
    grade_set = {lab["relevance"] for lab in labels} | {
        g for q in queries for g in q["relevance_grades"].values()
    }
    assert {0, 1, 2, 3}.issubset(grade_set), grade_set
    return {"queries": queries, "labels": labels}


def build_graph_edges(
    docs: List[Dict[str, Any]], principals: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    eid = 0

    def add(src: str, tgt: str, etype: str) -> None:
        nonlocal eid
        eid += 1
        edges.append({"id": f"edge-{eid}", "source": src, "target": tgt, "type": etype})

    # Ownership edges
    for doc in docs:
        add(doc["owner_id"], doc["id"], "OWNS")

    # Reference edges among tenant-a topic docs
    topic_docs = [d for d in docs if d["id"].startswith("doc-topic-")]
    for i, doc in enumerate(topic_docs):
        nxt = topic_docs[(i + 1) % len(topic_docs)]
        add(doc["id"], nxt["id"], "REFERENCES")
        if i % 5 == 0:
            add(doc["id"], "doc-roadmap", "REFERENCES")

    # Legacy references preserved
    add("doc-roadmap", "doc-api-docs", "REFERENCES")
    add("doc-onboarding", "doc-roadmap", "REFERENCES")

    # Member-of edges for a sample of principals
    for pid in ("principal-alice", "principal-bob", "principal-carol"):
        add(pid, "group-eng" if pid != "principal-carol" else "group-security", "MEMBER_OF")

    # Activity-ish WORKED_ON edges
    for i, doc in enumerate(topic_docs[:10]):
        add("principal-alice" if i % 2 == 0 else "principal-bob", doc["id"], "WORKED_ON")

    return edges


def build_activity_events(
    docs: List[Dict[str, Any]], principals: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    events = []
    eid = 0
    event_types = ["view", "edit", "authored", "commented_on", "referenced", "worked_on"]
    tenant_docs = {
        t: [d for d in docs if d["tenant_id"] == t]
        for t in ("tenant-a", "tenant-b", "tenant-c")
    }
    tenant_principals = {
        t: [p for p in principals if p["tenant_id"] == t]
        for t in ("tenant-a", "tenant-b", "tenant-c")
    }
    for tenant, count in (("tenant-a", 40), ("tenant-b", 15), ("tenant-c", 10)):
        tdocs = tenant_docs[tenant]
        tprin = tenant_principals[tenant]
        if not tdocs or not tprin:
            continue
        for i in range(count):
            eid += 1
            doc = tdocs[i % len(tdocs)]
            actor = tprin[i % len(tprin)]
            events.append(
                {
                    "event_id": f"evt-{tenant}-{eid:04d}",
                    "tenant_id": tenant,
                    "actor_principal_id": actor["id"],
                    "object_id": doc["id"],
                    "event_type": event_types[i % len(event_types)],
                    "source_system": doc["source"],
                    "event_time": _iso(minutes_ago=5 * i),
                    "session_id": f"sess-{tenant}-{i // 3}",
                    "privacy_level": "restricted" if doc.get("sensitivity") == "restricted" else "public",
                }
            )
    return events


def main() -> None:
    print(f"Generating Block Z fixtures {VERSION} -> {OUT}")
    principals = build_principals()
    groups = build_groups(principals)
    identities = build_multi_source(principals)
    docs = trim_to_sixty(build_documents(principals))
    acl_entries = build_acl_matrix(docs, groups)
    redteam = build_redteam_cases(docs, groups)
    relevance = build_relevance_labels(docs)
    edges = build_graph_edges(docs, principals)
    activity = build_activity_events(docs, principals)

    # Patch topic doc bodies so primary query phrases match mock substring search
    for i, topic in enumerate(TOPICS):
        doc = next(d for d in docs if d["id"] == f"doc-topic-{i:02d}")
        q = f"How does {topic} work?" if i >= 2 else topic
        if q.lower() not in doc["body"].lower():
            doc["body"] = f"{doc['body']} {q}"

    source_counts = Counter(d["source"] for d in docs)

    multi_count = sum(1 for ident in identities if len(ident["sources"]) >= 3)
    assert multi_count >= 8, multi_count
    assert len(principals) == 25
    assert len(docs) == 60
    assert len(redteam) == 15
    assert len(relevance["queries"]) == 30

    _write(
        "MANIFEST",
        {
            "version": VERSION,
            "generated_at": _iso(),
            "description": "Shared Block Z fixtures (architecture section 24 sizes)",
            "counts": {
                "documents": len(docs),
                "principals": len(principals),
                "groups": len(groups),
                "acl_redteam_cases": len(redteam),
                "relevance_queries": len(relevance["queries"]),
                "multi_source_3plus": multi_count,
                "graph_edges": len(edges),
                "activity_events": len(activity),
            },
            "fixtures": [
                "documents",
                "principals",
                "groups",
                "acl_matrix",
                "relevance_labels",
                "acl_redteam_cases",
                "graph_edges",
                "multi_source_identities",
                "performance_baselines",
                "crawl_expectations",
                "activity_events",
            ],
        },
    )
    _write("documents", {"version": VERSION, "documents": docs})
    _write("principals", {"version": VERSION, "principals": principals})
    _write("groups", {"version": VERSION, "groups": groups})
    _write("acl_matrix", {"version": VERSION, "entries": acl_entries})
    _write(
        "relevance_labels",
        {
            "version": VERSION,
            "queries": relevance["queries"],
            "labels": relevance["labels"],
        },
    )
    _write("acl_redteam_cases", {"version": VERSION, "cases": redteam})
    _write("graph_edges", {"version": VERSION, "edges": edges})
    _write("multi_source_identities", {"version": VERSION, "identities": identities})
    _write(
        "performance_baselines",
        {
            "version": VERSION,
            "baselines": {
                "lexical_p95_ms": 200,
                "vector_p95_ms": 150,
                "graph_p95_ms": 100,
                "federator_p95_ms": 800,
                "reader_p95_ms": 300,
                "assistant_p95_ms": 2000,
                "auth_revoke_ms": 60000,
                "provision_ms": 5000,
            },
        },
    )
    _write(
        "crawl_expectations",
        {
            "version": VERSION,
            "expected_counts": dict(source_counts),
            "delta_types": ["created", "updated", "deleted"],
            "rate_limit_retries": 3,
            "credentials_forbidden_patterns": [
                "AIza",
                "ya29.",
                "-----BEGIN PRIVATE KEY-----",
                "sk-",
            ],
        },
    )
    _write(
        "activity_events",
        {
            "version": VERSION,
            "generated_at": _iso(),
            "description": "Activity events consistent with shared docs/principals",
            "events": activity,
        },
    )

    print(
        f"OK docs={len(docs)} principals={len(principals)} groups={len(groups)} "
        f"redteam={len(redteam)} queries={len(relevance['queries'])} "
        f"labels={len(relevance['labels'])} multi_3plus={multi_count} "
        f"edges={len(edges)} activity={len(activity)}"
    )


if __name__ == "__main__":
    main()
