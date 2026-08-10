"""Generate deterministic Block-Z-shaped fixtures for Block G signoff."""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

DIM = 64
TENANT = "tenant_g_test"
MODEL_V1 = "text-embedding-3-large"
MODEL_V2 = "text-embedding-3-large-v2"
OUT = Path(__file__).resolve().parent

TOPICS = [
    "kubernetes", "postgres", "oauth", "vector_search", "acl",
    "chunking", "embeddings", "kafka", "redis", "fastapi",
    "tenancy", "observability", "backup", "encryption", "scim",
    "gmail", "drive", "indexing", "hnsw", "latency",
    "recall", "federator", "graph", "rag", "tokenizer",
    "celery", "alembic", "qdrant", "jwt", "rbac",
]


def unit(vec):
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def topic_base(i: int, seed: int = 42):
    rng = random.Random(seed + i * 17)
    v = [rng.gauss(0, 1) for _ in range(DIM)]
    # Make topic i dominate dimension i % DIM
    v[i % DIM] += 8.0
    return unit(v)


def near(base, seed: int, noise: float = 0.05):
    rng = random.Random(seed)
    v = [b + rng.gauss(0, noise) for b in base]
    return unit(v)


def far(seed: int):
    rng = random.Random(seed)
    return unit([rng.gauss(0, 1) for _ in range(DIM)])


chunks = []
# 30 topic-aligned public chunks + distractors + restricted
for i, topic in enumerate(TOPICS):
    base = topic_base(i)
    chunk_id = f"chunk-public-{i:02d}"
    chunks.append({
        "tenant_id": TENANT,
        "chunk_id": chunk_id,
        "document_id": f"doc-{topic}",
        "embedding": near(base, seed=1000 + i, noise=0.02),
        "embedding_v2": near(base, seed=2000 + i, noise=0.03),
        "model_version": MODEL_V1,
        "chunk_text": f"Authoritative guide to {topic.replace('_', ' ')} in Sync AI platform.",
        "acl_filter_terms": ["group:eng", "user:alice", f"group:topic-{topic}"],
        "metadata": {"topic": topic, "sensitivity": "public"},
        "topic_index": i,
    })

# Distractors (same tenant, open ACL, orthogonal vectors)
for j in range(40):
    chunks.append({
        "tenant_id": TENANT,
        "chunk_id": f"chunk-distractor-{j:02d}",
        "document_id": f"doc-noise-{j}",
        "embedding": far(seed=5000 + j),
        "embedding_v2": far(seed=6000 + j),
        "model_version": MODEL_V1,
        "chunk_text": f"Unrelated noise document {j} about weather and cooking.",
        "acl_filter_terms": ["group:eng", "user:alice"],
        "metadata": {"topic": "noise", "sensitivity": "public"},
        "topic_index": None,
    })

# Restricted / secret chunks for ACL red-team
restricted_ids = []
for k in range(20):
    cid = f"chunk-restricted-{k:02d}"
    restricted_ids.append(cid)
    chunks.append({
        "tenant_id": TENANT,
        "chunk_id": cid,
        "document_id": f"doc-secret-{k}",
        "embedding": far(seed=7000 + k),
        "embedding_v2": far(seed=8000 + k),
        "model_version": MODEL_V1,
        "chunk_text": f"CONFIDENTIAL payroll and M&A details {k}.",
        "acl_filter_terms": ["group:legal", "group:exec", "user:cfo"],
        "metadata": {"topic": "secret", "sensitivity": "restricted"},
        "topic_index": None,
    })

# Relevance labels: 30 queries, each maps to its topic public chunk
queries = []
for i, topic in enumerate(TOPICS):
    base = topic_base(i)
    qid = f"query-{i:02d}"
    relevant = [f"chunk-public-{i:02d}"]
    # occasionally add a second near neighbor from adjacent topic? keep single GT for clarity
    queries.append({
        "query_id": qid,
        "query_text": f"How does {topic.replace('_', ' ')} work?",
        "tenant_id": TENANT,
        "principal_id": "user:alice",
        "acl_filter_terms": ["group:eng", "user:alice"],
        "query_embedding": near(base, seed=9000 + i, noise=0.01),
        "model_version": MODEL_V1,
        "relevant_chunk_ids": relevant,
        "top_k": 10,
    })

# ACL red-team: 15 cases — user without legal/exec ACL must get 0 restricted hits
redteam = []
for n in range(15):
    # Aim query vector toward a restricted chunk so ANN would hit it without ACL
    restricted = restricted_ids[n]
    # Find restricted chunk embedding
    rchunk = next(c for c in chunks if c["chunk_id"] == restricted)
    redteam.append({
        "case_id": f"acl-redteam-{n:02d}",
        "description": f"User without legal ACL must not retrieve {restricted}",
        "tenant_id": TENANT,
        "principal_id": "user:bob",
        "acl_filter_terms": ["group:eng", "user:bob"],
        "query_embedding": rchunk["embedding"],
        "model_version": MODEL_V1,
        "top_k": 50,
        "forbidden_chunk_ids": restricted_ids,
        "must_return_zero_from_forbidden": True,
    })

corpus = {
    "tenant_id": TENANT,
    "dimensions": DIM,
    "model_versions": [MODEL_V1, MODEL_V2],
    "chunks": chunks,
    "fixture_provenance": "block-g-local (Block Z shared package absent; schema matches master prompt)",
}

(OUT / "corpus_chunks.json").write_text(json.dumps(corpus, indent=2), encoding="utf-8")
(OUT / "relevance_labels.json").write_text(
    json.dumps({"version": "1.0", "queries": queries, "fixture_provenance": corpus["fixture_provenance"]}, indent=2),
    encoding="utf-8",
)
(OUT / "acl_redteam_cases.json").write_text(
    json.dumps({"version": "1.0", "cases": redteam, "fixture_provenance": corpus["fixture_provenance"]}, indent=2),
    encoding="utf-8",
)
print(f"Wrote {len(chunks)} chunks, {len(queries)} queries, {len(redteam)} redteam cases -> {OUT}")