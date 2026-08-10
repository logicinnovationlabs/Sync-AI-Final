# Block F Integration Guide (for Block J / K / L)

## Service

- **Base URL (dev):** `http://localhost:8086`
- **Health:** `GET /health`
- **Search:** `POST /search/lexical` (also `POST /api/v1/search/lexical`)
- **Index:** `POST /_internal/index`

## Auth

Send Block A JWT bearer. `tenant_id` in the body must match the token.
In `ENVIRONMENT=test`, missing bearer uses a stub principal.

## Search request

```json
{
  "query": "getUserInfo oauth",
  "tenant_id": "tenant_f_test",
  "user_id": "user:alice",
  "acl_terms": ["group:eng", "user:alice"],
  "filters": {
    "object_type": ["code"],
    "source": ["github"]
  },
  "facets": ["object_type", "source", "repository", "owner", "language", "tags"],
  "from": 0,
  "size": 20
}
```

## Critical ACL rule

`acl_terms` are applied in **filter context before retrieval**. Empty `acl_terms` returns zero hits (fail-closed). Never post-filter as the sole ACL check.

## Indexing

Canonical documents arrive via `ingest.canonical.v1` (`CanonicalConsumer`) or HTTP:

```json
{
  "document_id": "doc-1",
  "tenant_id": "tenant_f_test",
  "fields": {
    "title": "...",
    "body_text": "...",
    "acl_filter_terms": ["group:eng", "user:alice"]
  }
}
```

## Backends

| Env | Value | Use |
|-----|-------|-----|
| `SEARCH_BACKEND` | `mock` | In-memory BM25 (Phase 1 signoff) |
| `SEARCH_BACKEND` | `opensearch` | OpenSearch cluster (Phase 2) |
