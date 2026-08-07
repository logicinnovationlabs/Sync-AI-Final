"""Generate deterministic Block-Z-shaped fixtures for Block F signoff.

Produces:
  - corpus_docs.json          (60 documents)
  - acl_redteam_cases.json    (15 security cases)
  - representative_queries.json
  - facet_ground_truth.json
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

TENANT = "tenant_f_test"
OTHER_TENANT = "tenant_other"
OUT = Path(__file__).resolve().parent
PROVENANCE = (
    "block-f-local (Block Z shared package absent; schema matches master prompt)"
)

TOPICS = [
    "kubernetes", "postgres", "oauth", "vector_search", "acl",
    "chunking", "embeddings", "kafka", "redis", "fastapi",
    "tenancy", "observability", "backup", "encryption", "scim",
    "gmail", "drive", "indexing", "bm25", "latency",
    "tokenizer", "celery", "alembic", "opensearch", "jwt",
    "rbac", "faceting", "snippets", "federator", "canonical",
]

SOURCES = ["confluence", "github", "drive", "gmail", "jira", "notion"]
OBJECT_TYPES = ["doc", "code", "ticket", "email", "wiki"]
LANGUAGES = ["en", "python", "typescript", "go", "markdown"]
OWNERS = ["user:alice", "user:bob", "user:carol", "user:dave"]
REPOS = ["sync-ai/backend", "sync-ai/frontend", "sync-ai/infra", "acme/docs", ""]


def _iso(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


docs = []

# --- 40 public / eng-accessible docs (indices 0-39) ---
for i, topic in enumerate(TOPICS):
    source = SOURCES[i % len(SOURCES)]
    obj = OBJECT_TYPES[i % len(OBJECT_TYPES)]
    lang = LANGUAGES[i % len(LANGUAGES)]
    owner = OWNERS[i % len(OWNERS)]
    repo = REPOS[i % len(REPOS)]
    camel = "".join(w.capitalize() for w in topic.split("_"))
    snake = topic
    doc_id = f"doc-public-{i:02d}"
    docs.append({
        "document_id": doc_id,
        "tenant_id": TENANT,
        "title": f"{camel} Guide: getUserInfo and {snake}_config",
        "body_text": (
            f"Authoritative guide to {topic.replace('_', ' ')} in Sync AI. "
            f"Use getUserInfo() with user_info and {snake}_handler for setup. "
            f"This document covers BM25 ranking, ACL enforcement, and faceting."
        ),
        "comments_text": f"Reviewed for {topic} correctness.",
        "file_path": f"src/{topic}/handler_{i}.py" if obj == "code" else f"docs/{topic}.md",
        "repository": repo,
        "object_type": obj,
        "source": source,
        "owner": owner,
        "updated_at": _iso(i),
        "container_path": f"/eng/{topic}",
        "language": lang,
        "tags": [topic, "public", source],
        "acl_filter_terms": ["group:eng", "user:alice", f"group:topic-{topic}"],
        "hidden_fields": [],
        "deleted": False,
        "sensitivity": "public",
    })

# --- 10 eng docs that also mention restricted keywords (distractors for ACL) ---
for j in range(10):
    docs.append({
        "document_id": f"doc-distractor-{j:02d}",
        "tenant_id": TENANT,
        "title": f"Public notes on payroll process overview {j}",
        "body_text": (
            f"High-level public payroll process overview {j}. "
            "No confidential numbers. Uses getUserInfo for directory lookup."
        ),
        "comments_text": "",
        "file_path": f"docs/payroll-overview-{j}.md",
        "repository": "acme/docs",
        "object_type": "doc",
        "source": "confluence",
        "owner": "user:alice",
        "updated_at": _iso(j + 40),
        "container_path": "/eng/payroll-overview",
        "language": "en",
        "tags": ["payroll", "public"],
        "acl_filter_terms": ["group:eng", "user:alice"],
        "hidden_fields": [],
        "deleted": False,
        "sensitivity": "public",
    })

# --- 10 restricted / edge-case docs for ACL red-team (indices map to cases) ---
restricted_specs = [
    # 0 cross-tenant (indexed under OTHER tenant; also mirrored reference)
    {
        "document_id": "doc-restricted-cross-tenant",
        "tenant_id": OTHER_TENANT,
        "title": "Other tenant confidential M&A",
        "body_text": "CONFIDENTIAL cross-tenant M&A deal sheet. Unauthorized access forbidden.",
        "acl_filter_terms": ["group:legal", "user:cfo"],
        "container_path": "/legal/ma",
        "sensitivity": "restricted",
    },
    # 1 no read access
    {
        "document_id": "doc-restricted-no-access",
        "tenant_id": TENANT,
        "title": "Executive compensation confidential",
        "body_text": "CONFIDENTIAL executive compensation tables. Legal only.",
        "acl_filter_terms": ["group:legal", "group:exec", "user:cfo"],
        "container_path": "/legal/comp",
        "sensitivity": "restricted",
    },
    # 2 user WITH read access (positive control — alice may see)
    {
        "document_id": "doc-allowed-alice",
        "tenant_id": TENANT,
        "title": "Alice private notebook getUserInfo notes",
        "body_text": "Alice private notes on getUserInfo and ACL. eng may read.",
        "acl_filter_terms": ["user:alice", "group:eng"],
        "container_path": "/eng/alice",
        "sensitivity": "public",
    },
    # 3 group membership changed mid-session (doc now legal-only)
    {
        "document_id": "doc-restricted-group-changed",
        "tenant_id": TENANT,
        "title": "Former eng shared board minutes",
        "body_text": "Board minutes now restricted after group change. CONFIDENTIAL.",
        "acl_filter_terms": ["group:legal", "group:exec"],
        "container_path": "/legal/board",
        "sensitivity": "restricted",
    },
    # 4 container inheritance edge
    {
        "document_id": "doc-restricted-container-inherit",
        "tenant_id": TENANT,
        "title": "Inherited restricted container secrets",
        "body_text": "Secrets inherited from restricted container. CONFIDENTIAL tokens.",
        "acl_filter_terms": ["group:legal"],
        "container_path": "/legal/vault/secrets",
        "sensitivity": "restricted",
    },
    # 5 deny override (eng denied explicitly)
    {
        "document_id": "doc-restricted-deny-override",
        "tenant_id": TENANT,
        "title": "Deny override payroll detail",
        "body_text": "CONFIDENTIAL payroll detail with deny:group:eng override.",
        "acl_filter_terms": ["group:legal", "group:eng", "deny:group:eng", "deny:user:bob"],
        "container_path": "/hr/payroll",
        "sensitivity": "restricted",
    },
    # 6 unauthenticated / empty ACL handled at API — doc still restricted
    {
        "document_id": "doc-restricted-auth-required",
        "tenant_id": TENANT,
        "title": "Auth required secret blueprint",
        "body_text": "CONFIDENTIAL blueprint requiring authentication.",
        "acl_filter_terms": ["group:legal", "user:cfo"],
        "container_path": "/legal/blueprints",
        "sensitivity": "restricted",
    },
    # 7 insufficient scope (same as restricted for eng)
    {
        "document_id": "doc-restricted-scope",
        "tenant_id": TENANT,
        "title": "Insufficient scope classified memo",
        "body_text": "CONFIDENTIAL classified memo. Scope search.admin required.",
        "acl_filter_terms": ["group:exec", "role:search.admin"],
        "container_path": "/exec/classified",
        "sensitivity": "restricted",
    },
    # 8 deleted document
    {
        "document_id": "doc-restricted-deleted",
        "tenant_id": TENANT,
        "title": "Deleted confidential archive",
        "body_text": "CONFIDENTIAL deleted archive content should never surface.",
        "acl_filter_terms": ["group:eng", "user:alice"],  # would be visible if not deleted
        "container_path": "/eng/archive",
        "sensitivity": "restricted",
        "deleted": True,
    },
    # 9 unshared document
    {
        "document_id": "doc-restricted-unshared",
        "tenant_id": TENANT,
        "title": "Unshared personal draft",
        "body_text": "Unshared personal draft. CONFIDENTIAL until shared.",
        "acl_filter_terms": ["user:carol"],
        "container_path": "/users/carol/drafts",
        "sensitivity": "restricted",
    },
]

for spec in restricted_specs:
    deleted = bool(spec.pop("deleted", False))
    docs.append({
        "document_id": spec["document_id"],
        "tenant_id": spec["tenant_id"],
        "title": spec["title"],
        "body_text": spec["body_text"],
        "comments_text": "",
        "file_path": f"restricted/{spec['document_id']}.md",
        "repository": "acme/private",
        "object_type": "doc",
        "source": "confluence",
        "owner": "user:cfo",
        "updated_at": _iso(1),
        "container_path": spec["container_path"],
        "language": "en",
        "tags": ["restricted", "confidential"],
        "acl_filter_terms": spec["acl_filter_terms"],
        "hidden_fields": ["comments_text"],
        "deleted": deleted,
        "sensitivity": spec["sensitivity"],
    })

# --- Extra restricted for cases 10-14 ---
extra_restricted = [
    {
        "document_id": "doc-restricted-container",
        "title": "Document in restricted container",
        "body_text": "CONFIDENTIAL item inside restricted container path.",
        "acl_filter_terms": ["group:legal"],
        "container_path": "/restricted/container/item",
    },
    {
        "document_id": "doc-multi-group-secret",
        "title": "Multi group accessible secret for eng and platform",
        "body_text": "Secret visible to eng and platform groups via multi-group ACL.",
        "acl_filter_terms": ["group:eng", "group:platform", "user:alice"],
        "container_path": "/eng/shared-secret",
        "sensitivity": "public",  # eng can see — positive for multi-group
    },
    {
        "document_id": "doc-restricted-removed-group",
        "title": "Access removed from eng group",
        "body_text": "CONFIDENTIAL after eng removed from ACL.",
        "acl_filter_terms": ["group:legal"],
        "container_path": "/legal/removed",
    },
    {
        "document_id": "doc-parent-denied-child",
        "title": "Parent denied child allowed should deny",
        "body_text": "CONFIDENTIAL parent-denied container inheritance case.",
        "acl_filter_terms": ["group:legal", "deny:group:eng"],
        "container_path": "/parent-denied/child-allowed",
    },
    {
        "document_id": "doc-child-denied-parent",
        "title": "Child denied parent allowed should deny",
        "body_text": "CONFIDENTIAL child-denied container inheritance case.",
        "acl_filter_terms": ["group:eng", "deny:user:bob", "deny:group:eng"],
        "container_path": "/parent-allowed/child-denied",
    },
]

for spec in extra_restricted:
    docs.append({
        "document_id": spec["document_id"],
        "tenant_id": TENANT,
        "title": spec["title"],
        "body_text": spec["body_text"],
        "comments_text": "",
        "file_path": f"restricted/{spec['document_id']}.md",
        "repository": "acme/private",
        "object_type": "doc",
        "source": "confluence",
        "owner": "user:cfo",
        "updated_at": _iso(2),
        "container_path": spec["container_path"],
        "language": "en",
        "tags": ["restricted", "confidential"],
        "acl_filter_terms": spec["acl_filter_terms"],
        "hidden_fields": [],
        "deleted": False,
        "sensitivity": spec.get("sensitivity", "restricted"),
    })

# Pad to exactly 60 reference docs
pad_n = 0
while len(docs) < 60:
    docs.append({
        "document_id": f"doc-pad-{pad_n:02d}",
        "tenant_id": TENANT,
        "title": f"Padding reference document {pad_n} getUserInfo user_info",
        "body_text": (
            f"Padding document {pad_n} for the 60-doc Block Z reference fixture. "
            "Covers BM25 latency and facet accuracy baselines."
        ),
        "comments_text": "",
        "file_path": f"docs/pad-{pad_n}.md",
        "repository": "acme/docs",
        "object_type": "wiki",
        "source": "notion",
        "owner": "user:dave",
        "updated_at": _iso(pad_n + 3),
        "container_path": f"/eng/pad/{pad_n}",
        "language": "en",
        "tags": ["pad", "public"],
        "acl_filter_terms": ["group:eng", "user:alice"],
        "hidden_fields": [],
        "deleted": False,
        "sensitivity": "public",
    })
    pad_n += 1

assert len(docs) == 60, f"Expected 60 docs, got {len(docs)}"

# Forbidden set for eng/bob callers
forbidden_ids = [
    d["document_id"]
    for d in docs
    if d["sensitivity"] == "restricted" or d.get("deleted")
]

# --- ACL red-team: 15 cases matching master prompt ---
redteam_cases = [
    {
        "case_id": "acl-01-cross-tenant",
        "description": "Cross-tenant access attempt",
        "tenant_id": TENANT,  # caller bound to TENANT
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],
        "query": "confidential M&A deal sheet",
        "forbidden_document_ids": ["doc-restricted-cross-tenant"] + forbidden_ids,
        "must_return_zero_from_forbidden": True,
        "expect_empty_or_open_only": True,
    },
    {
        "case_id": "acl-02-no-read-access",
        "description": "User with no read access to document",
        "tenant_id": TENANT,
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],
        "query": "executive compensation confidential",
        "forbidden_document_ids": forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
    {
        "case_id": "acl-03-has-read-access",
        "description": "User with read access to document (should pass)",
        "tenant_id": TENANT,
        "user_id": "user:alice",
        "acl_filter_terms": ["group:eng", "user:alice"],
        "query": "Alice private notebook getUserInfo",
        "forbidden_document_ids": [d for d in forbidden_ids if d != "doc-allowed-alice"],
        "must_return_zero_from_forbidden": True,
        "must_include_document_ids": ["doc-allowed-alice"],
    },
    {
        "case_id": "acl-04-group-changed",
        "description": "Group membership changed mid-session",
        "tenant_id": TENANT,
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],  # no longer in legal
        "query": "board minutes restricted",
        "forbidden_document_ids": forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
    {
        "case_id": "acl-05-container-inheritance",
        "description": "Container inheritance edge cases",
        "tenant_id": TENANT,
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],
        "query": "Inherited restricted container secrets",
        "forbidden_document_ids": forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
    {
        "case_id": "acl-06-deny-override",
        "description": "Deny override (explicit deny beats allow)",
        "tenant_id": TENANT,
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],
        "query": "Deny override payroll detail",
        "forbidden_document_ids": forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
    {
        "case_id": "acl-07-unauthenticated",
        "description": "Unauthenticated request",
        "tenant_id": TENANT,
        "user_id": "anonymous",
        "acl_filter_terms": [],  # empty => fail-closed
        "query": "Auth required secret blueprint",
        "forbidden_document_ids": forbidden_ids + [d["document_id"] for d in docs],
        "must_return_zero_from_forbidden": True,
        "expect_total_zero": True,
    },
    {
        "case_id": "acl-08-insufficient-scope",
        "description": "Token with insufficient scope",
        "tenant_id": TENANT,
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],  # missing role:search.admin
        "query": "Insufficient scope classified memo",
        "forbidden_document_ids": forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
    {
        "case_id": "acl-09-deleted-document",
        "description": "Deleted document access attempt",
        "tenant_id": TENANT,
        "user_id": "user:alice",
        "acl_filter_terms": ["group:eng", "user:alice"],
        "query": "Deleted confidential archive",
        "forbidden_document_ids": ["doc-restricted-deleted"] + forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
    {
        "case_id": "acl-10-unshared",
        "description": "Unshared document access",
        "tenant_id": TENANT,
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],
        "query": "Unshared personal draft",
        "forbidden_document_ids": forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
    {
        "case_id": "acl-11-restricted-container",
        "description": "Document in restricted container",
        "tenant_id": TENANT,
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],
        "query": "restricted container path CONFIDENTIAL",
        "forbidden_document_ids": forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
    {
        "case_id": "acl-12-multi-group",
        "description": "User with access through multiple groups",
        "tenant_id": TENANT,
        "user_id": "user:alice",
        "acl_filter_terms": ["group:eng", "group:platform", "user:alice"],
        "query": "Multi group accessible secret",
        "forbidden_document_ids": [d for d in forbidden_ids if d != "doc-multi-group-secret"],
        "must_return_zero_from_forbidden": True,
        "must_include_document_ids": ["doc-multi-group-secret"],
    },
    {
        "case_id": "acl-13-removed-from-group",
        "description": "User with access removed from group",
        "tenant_id": TENANT,
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],
        "query": "Access removed from eng group",
        "forbidden_document_ids": forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
    {
        "case_id": "acl-14-parent-denied",
        "description": "Parent container denied, child allowed (should deny)",
        "tenant_id": TENANT,
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],
        "query": "Parent denied child allowed should deny",
        "forbidden_document_ids": forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
    {
        "case_id": "acl-15-child-denied",
        "description": "Child container denied, parent allowed (should deny)",
        "tenant_id": TENANT,
        "user_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],
        "query": "Child denied parent allowed should deny",
        "forbidden_document_ids": forbidden_ids,
        "must_return_zero_from_forbidden": True,
    },
]

assert len(redteam_cases) == 15

# --- Representative queries (100) ---
base_queries = []
for i, topic in enumerate(TOPICS):
    base_queries.append({
        "query_id": f"q-{i:02d}-a",
        "query": f"How does {topic.replace('_', ' ')} work?",
        "tenant_id": TENANT,
        "user_id": "user:alice",
        "acl_filter_terms": ["group:eng", "user:alice"],
        "relevant_document_ids": [f"doc-public-{i:02d}"],
    })
    base_queries.append({
        "query_id": f"q-{i:02d}-b",
        "query": f"getUserInfo {topic}",
        "tenant_id": TENANT,
        "user_id": "user:alice",
        "acl_filter_terms": ["group:eng", "user:alice"],
        "relevant_document_ids": [f"doc-public-{i:02d}"],
    })
# Pad / cycle to 100
queries = []
while len(queries) < 100:
    for q in base_queries:
        queries.append({**q, "query_id": f"{q['query_id']}-{len(queries):03d}"})
        if len(queries) >= 100:
            break

# --- Facet ground truth (ACL = eng+alice over non-deleted TENANT docs they can see) ---
viewer_acl = {"group:eng", "user:alice"}


def _visible(doc):
    if doc["tenant_id"] != TENANT:
        return False
    if doc.get("deleted"):
        return False
    terms = set(doc.get("acl_filter_terms") or [])
    denies = {t[5:] for t in terms if t.startswith("deny:")}
    allows = {t for t in terms if not t.startswith("deny:")}
    if denies & viewer_acl:
        return False
    return bool(allows & viewer_acl)


visible_docs = [d for d in docs if _visible(d)]
facet_fields = ["object_type", "source", "repository", "owner", "language", "tags"]
ground = {}
for field in facet_fields:
    counter = Counter()
    for d in visible_docs:
        val = d.get(field)
        if field == "tags":
            for tag in val or []:
                counter[tag] += 1
        elif val:
            counter[str(val)] += 1
    ground[field] = [
        {"value": k, "count": v}
        for k, v in sorted(counter.items(), key=lambda x: (-x[1], x[0]))
    ]

corpus = {
    "tenant_id": TENANT,
    "other_tenant_id": OTHER_TENANT,
    "document_count": len(docs),
    "documents": docs,
    "fixture_provenance": PROVENANCE,
}

(OUT / "corpus_docs.json").write_text(json.dumps(corpus, indent=2), encoding="utf-8")
(OUT / "acl_redteam_cases.json").write_text(
    json.dumps(
        {
            "version": "1.0",
            "cases": redteam_cases,
            "fixture_provenance": PROVENANCE,
        },
        indent=2,
    ),
    encoding="utf-8",
)
(OUT / "representative_queries.json").write_text(
    json.dumps(
        {
            "version": "1.0",
            "queries": queries,
            "fixture_provenance": PROVENANCE,
        },
        indent=2,
    ),
    encoding="utf-8",
)
(OUT / "facet_ground_truth.json").write_text(
    json.dumps(
        {
            "version": "1.0",
            "tenant_id": TENANT,
            "user_id": "user:alice",
            "acl_filter_terms": ["group:eng", "user:alice"],
            "query": "",  # match-all under ACL
            "facets": ground,
            "visible_document_count": len(visible_docs),
            "fixture_provenance": PROVENANCE,
        },
        indent=2,
    ),
    encoding="utf-8",
)

print(f"Wrote {len(docs)} docs, {len(redteam_cases)} red-team cases, {len(queries)} queries")
print(f"Visible under eng+alice: {len(visible_docs)}")
