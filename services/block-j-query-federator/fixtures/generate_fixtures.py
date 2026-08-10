"""Generate Block-Z-shaped fixtures for Block J signoff (J1-J4)."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent
PROVENANCE = (
    "block-j-local (Block Z shared package absent; schema matches master prompt)"
)

TOPICS = [
    "kubernetes",
    "postgres",
    "oauth",
    "kafka",
    "redis",
    "graphql",
    "terraform",
    "prometheus",
    "elasticsearch",
    "docker",
    "grpc",
    "s3",
    "iam",
    "cicd",
    "feature flags",
    "rate limiting",
    "circuit breaker",
    "saga pattern",
    "event sourcing",
    "vector search",
    "bm25 ranking",
    "acl inheritance",
    "tenant isolation",
    "jwt auth",
    "scim sync",
    "webhook delivery",
    "chunk embeddings",
    "knowledge graph",
    "snippet generation",
    "hybrid retrieval",
]

TENANT = "tenant_j_test"
ALICE = "user:alice"
BOB = "user:bob"
ENG = "group:eng"
LEGAL = "group:legal"
EXEC = "group:exec"


def _embed(text: str, dims: int = 64) -> list:
    digest = hashlib.sha256(text.lower().encode()).digest()
    values = []
    seed = digest
    while len(values) < dims:
        for b in seed:
            values.append((b / 127.5) - 1.0)
            if len(values) >= dims:
                break
        seed = hashlib.sha256(seed).digest()
    for token in text.lower().split():
        th = hashlib.md5(token.encode()).digest()
        for i, b in enumerate(th):
            values[i % dims] += ((b / 255.0) - 0.5) * 0.25
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values[:dims]]


documents = []
acl_entries = []

for i, topic in enumerate(TOPICS):
    doc_id = f"doc-public-{i:02d}"
    title = f"{topic.title()} guide"
    body = (
        f"How does {topic} work? This document explains {topic} in depth. "
        f"getUserInfo {topic} reference for engineers. "
        f"Operational runbook covering {topic} best practices and failure modes."
    )
    documents.append(
        {
            "document_id": doc_id,
            "tenant_id": TENANT,
            "title": title,
            "body_text": body,
            "snippet": body[:200],
            "object_type": "doc",
            "source": "wiki",
            "owner": ALICE,
            "acl_filter_terms": [ENG, ALICE],
            "tags": [topic.split()[0], "eng"],
            "lexical_base_score": 12.0 - (i % 5) * 0.3,
            "vector_base_score": 0.92 - (i % 7) * 0.02,
            "graph_boost": 0.15 if i % 3 == 0 else 0.05,
        }
    )
    acl_entries.append(
        {
            "doc_id": doc_id,
            "principal_id": ALICE,
            "group_id": None,
            "permission_type": "read",
            "is_deny": False,
            "tenant_id": TENANT,
        }
    )
    acl_entries.append(
        {
            "doc_id": doc_id,
            "principal_id": None,
            "group_id": ENG,
            "permission_type": "read",
            "is_deny": False,
            "tenant_id": TENANT,
        }
    )

RESTRICTED = [
    ("doc-restricted-cross-tenant", "confidential M&A deal sheet", "tenant_other"),
    ("doc-restricted-no-access", "executive compensation confidential", TENANT),
    ("doc-restricted-group-changed", "legal hold privileged memo", TENANT),
    ("doc-restricted-container-inherit", "board minutes confidential", TENANT),
    ("doc-restricted-deny-override", "payroll secrets spreadsheet", TENANT),
    ("doc-restricted-auth-required", "SSO breakglass credentials", TENANT),
    ("doc-restricted-scope", "security audit findings restricted", TENANT),
    ("doc-restricted-deleted", "deleted secret incident report", TENANT),
    ("doc-restricted-unshared", "unshared private notebook", TENANT),
    ("doc-restricted-container", "HR folder performance reviews", TENANT),
    ("doc-restricted-removed-group", "former group exclusive notes", TENANT),
    ("doc-parent-denied-child", "parent denied child visible trap", TENANT),
    ("doc-child-denied-parent", "child denied parent visible trap", TENANT),
    ("doc-restricted-exec-only", "CEO strategy confidential", TENANT),
    ("doc-restricted-legal-only", "attorney client privileged brief", TENANT),
]

for doc_id, title, tenant in RESTRICTED:
    body = f"{title}. Restricted content that eng users must never see in search."
    documents.append(
        {
            "document_id": doc_id,
            "tenant_id": tenant,
            "title": title,
            "body_text": body,
            "snippet": body[:200],
            "object_type": "doc",
            "source": "drive",
            "owner": "user:exec",
            "acl_filter_terms": [LEGAL, EXEC, "user:exec"],
            "tags": ["restricted", "confidential"],
            "lexical_base_score": 20.0,
            "vector_base_score": 0.99,
            "graph_boost": 0.5,
            "restricted": True,
        }
    )
    for group in (LEGAL, EXEC):
        acl_entries.append(
            {
                "doc_id": doc_id,
                "principal_id": None,
                "group_id": group,
                "permission_type": "read",
                "is_deny": False,
                "tenant_id": tenant,
            }
        )
    acl_entries.append(
        {
            "doc_id": doc_id,
            "principal_id": "user:exec",
            "group_id": None,
            "permission_type": "read",
            "is_deny": False,
            "tenant_id": tenant,
        }
    )

documents.append(
    {
        "document_id": "doc-alice-private",
        "tenant_id": TENANT,
        "title": "Alice private notebook getUserInfo",
        "body_text": "Alice private notebook getUserInfo oauth notes.",
        "snippet": "Alice private notebook getUserInfo oauth notes.",
        "object_type": "doc",
        "source": "drive",
        "owner": ALICE,
        "acl_filter_terms": [ALICE],
        "tags": ["private"],
        "lexical_base_score": 15.0,
        "vector_base_score": 0.88,
        "graph_boost": 0.2,
    }
)
acl_entries.append(
    {
        "doc_id": "doc-alice-private",
        "principal_id": ALICE,
        "group_id": None,
        "permission_type": "read",
        "is_deny": False,
        "tenant_id": TENANT,
    }
)

FORBIDDEN_IDS = [r[0] for r in RESTRICTED]

redteam_cases = []
for n, (doc_id, title, _tenant) in enumerate(RESTRICTED, start=1):
    redteam_cases.append(
        {
            "case_id": f"acl-redteam-{n:02d}",
            "description": f"Eng user must not see {doc_id}",
            "tenant_id": TENANT,
            "user_id": BOB,
            "principal_id": BOB,
            "groups": [ENG],
            "acl_filter_terms": [ENG, BOB],
            "query": title,
            "forbidden_document_ids": FORBIDDEN_IDS,
            "must_return_zero_from_forbidden": True,
            "backend_combinations": [
                ["lexical", "vector", "graph"],
                ["lexical", "vector"],
                ["lexical", "graph"],
                ["vector", "graph"],
                ["lexical"],
                ["vector"],
            ],
        }
    )

assert len(redteam_cases) == 15

relevance_queries = []
for i, topic in enumerate(TOPICS):
    qtext = f"How does {topic} work?"
    relevance_queries.append(
        {
            "query_id": f"query-{i:02d}",
            "query_text": qtext,
            "tenant_id": TENANT,
            "principal_id": ALICE,
            "groups": [ENG],
            "acl_filter_terms": [ENG, ALICE],
            "query_embedding": _embed(qtext),
            "relevant_document_ids": [f"doc-public-{i:02d}"],
            "relevance_grades": {f"doc-public-{i:02d}": 3},
        }
    )
assert len(relevance_queries) == 30

rep_queries = []
templates = [
    "How does {t} work?",
    "getUserInfo {t}",
    "{t} best practices",
    "{t} failure modes",
]
for i in range(100):
    topic = TOPICS[i % len(TOPICS)]
    tmpl = templates[i % len(templates)]
    q = tmpl.format(t=topic)
    rep_queries.append(
        {
            "query_id": f"lat-{i:03d}",
            "query": q,
            "tenant_id": TENANT,
            "user_id": ALICE,
            "principal_id": ALICE,
            "acl_filter_terms": [ENG, ALICE],
            "groups": [ENG],
        }
    )

corpus = {
    "version": "1.0",
    "fixture_provenance": PROVENANCE,
    "documents": documents,
    "acl_entries": acl_entries,
}

(OUT / "corpus.json").write_text(json.dumps(corpus, indent=2), encoding="utf-8")
(OUT / "acl_entries.json").write_text(
    json.dumps(
        {"version": "1.0", "entries": acl_entries, "fixture_provenance": PROVENANCE},
        indent=2,
    ),
    encoding="utf-8",
)
(OUT / "acl_redteam_cases.json").write_text(
    json.dumps(
        {"version": "1.0", "cases": redteam_cases, "fixture_provenance": PROVENANCE},
        indent=2,
    ),
    encoding="utf-8",
)
(OUT / "relevance_labels.json").write_text(
    json.dumps(
        {
            "version": "1.0",
            "queries": relevance_queries,
            "fixture_provenance": PROVENANCE,
        },
        indent=2,
    ),
    encoding="utf-8",
)
(OUT / "representative_queries.json").write_text(
    json.dumps(
        {"version": "1.0", "queries": rep_queries, "fixture_provenance": PROVENANCE},
        indent=2,
    ),
    encoding="utf-8",
)

print(
    f"Wrote {len(documents)} docs, {len(acl_entries)} acl rows, "
    f"{len(redteam_cases)} redteam, {len(relevance_queries)} relevance, "
    f"{len(rep_queries)} latency queries -> {OUT}"
)
