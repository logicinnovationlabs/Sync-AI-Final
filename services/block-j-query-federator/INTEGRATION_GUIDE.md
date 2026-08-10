# Block J Integration Guide

## Endpoint

`POST /api/v1/search`

Base URL (local): `http://localhost:8089`

## Auth

Send Block A JWT as `Authorization: Bearer <token>`.

Required claims: `tenant_id`, `principal_id` (or `user_id`).  
Optional: `groups`, `scopes`, `acl_terms`.

In `ENVIRONMENT=test`, a missing bearer uses a stub principal (`tenant_j_test` / `user:alice`).

## Request

```json
{
  "query": "How does kubernetes work?",
  "tenant_id": "tenant_j_test",
  "filters": {"source": ["wiki"]},
  "facets": ["source", "object_type"],
  "from": 0,
  "size": 20
}
```

## Response

```json
{
  "results": [
    {
      "document_id": "doc-public-00",
      "score": 0.91,
      "title": "Kubernetes guide",
      "snippet": "How does kubernetes work? ...",
      "sources": ["lexical", "vector", "graph"],
      "citations": [{"document_id": "doc-public-00", "title": "Kubernetes guide"}]
    }
  ],
  "facets": {"source": [{"value": "wiki", "count": 30}]},
  "total": 12,
  "took_ms": 42.5,
  "degraded": false,
  "backends": [
    {"name": "lexical", "ok": true, "latency_ms": 12.0, "hit_count": 20},
    {"name": "vector", "ok": true, "latency_ms": 18.0, "hit_count": 20},
    {"name": "graph", "ok": true, "latency_ms": 5.0, "hit_count": 12}
  ]
}
```

## Downstream dependencies

| Block | Env | Endpoint used |
|-------|-----|---------------|
| F Lexical | `LEXICAL_SEARCH_URL` | `POST /search/lexical` |
| G Vector | `VECTOR_SEARCH_URL` | `POST /api/v1/search/vector` |
| H Graph | `GRAPH_SERVICE_URL` | `POST /graph/signals` |

Graph signals are optional; HTTP 404 yields empty boosts (degraded, not fatal).

## ACL post-check

After merge, Block J batch-queries `acl_entries` (`ACL_BACKEND=memory|postgres`) and
drops any candidate the caller cannot read. Fail-closed when no grant exists.
