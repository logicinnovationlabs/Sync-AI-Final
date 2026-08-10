# Block J Integration Guide — Vector Search Service (Block G)

## Endpoint

`POST /api/v1/search/vector`

Base URL (local): `http://localhost:8087`

## Auth

Send Block A JWT as `Authorization: Bearer <token>`.  
`tenant_id` in the body **must** match `tenant_id` in the token (403 on mismatch; 401 if token missing/invalid in non-test environments).

## Request Body (JSON)

```json
{
  "tenant_id": "tenant-123",
  "principal_id": "user-456",
  "acl_terms": ["group:eng", "user:456"],
  "query_embedding": [0.1, 0.2],
  "top_k": 100,
  "model_version": "text-embedding-3-large"
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `tenant_id` | yes | Must match JWT |
| `principal_id` | yes | Auditing / federator context |
| `acl_terms` | yes | Caller principals/groups from Block C; empty → empty results (fail-closed). Alias: `acl_filter_terms` |
| `query_embedding` | yes | Same dimensionality as ingested embeddings |
| `model_version` | no | If set, only that version is searched |
| `top_k` | no | Default 100, max 500 |
| `score_threshold` | no | Cosine similarity floor |

## Response Body (JSON)

```json
{
  "results": [
    {
      "chunk_id": "chunk-abc",
      "document_id": "doc-789",
      "score": 0.89,
      "model_version": "text-embedding-3-large",
      "chunk_text": "...",
      "metadata": {"source": "drive", "title": "..."}
    }
  ],
  "model_versions_used": ["text-embedding-3-large"]
}
```

### Federator rules

1. **Do not compare scores across `model_version` values.** Prefer filtering to the active embed model, or rank within each version separately.
2. ACL is applied **inside** Block G (Qdrant `MatchAny` on `acl_terms`). Do not rely on post-filtering alone.
3. Tenant isolation uses **per-tenant collections** (`tenant_{id}_chunks`).

## Error Handling

| Status | When |
|--------|------|
| 401 | Missing/invalid token (non-test) |
| 403 | Tenant binding failure (body `tenant_id` ≠ JWT) |
| 400 | Malformed request / validation errors |
| 500 | Internal failures (logged with `X-Request-ID` when provided) |

## Ingestion (Block E)

`POST /api/v1/ingest` with a single chunk or `{"chunks":[...]}` matching `ingest.chunks.v1`:

```json
{
  "tenant_id": "tenant-123",
  "chunk_id": "chunk-abc",
  "document_id": "doc-789",
  "embedding": [0.1, 0.2],
  "model_version": "text-embedding-3-large",
  "chunk_text": "...",
  "acl_filter_terms": ["group:eng"],
  "metadata": {}
}
```

`acl_terms` is accepted as an alias for `acl_filter_terms` on ingest.

Optional event path: consume `ingest.chunks.v1` via `app.events.handlers.handle_ingest_chunks_event`.

## Health

`GET /health` → `{"status":"healthy","vector_db_type":"qdrant",…}`

## Config for Block J

| Env | Example |
|-----|---------|
| `VECTOR_SEARCH_URL` | `http://block-g-vector-search:8087` |
| `VECTOR_DB_TYPE` | `qdrant` |
| `QDRANT_HOST` / `QDRANT_PORT` | `qdrant` / `6333` |

## Minimal Python caller

```python
import httpx

resp = httpx.post(
    "http://localhost:8087/api/v1/search/vector",
    headers={"Authorization": f"Bearer {jwt}"},
    json={
        "tenant_id": tenant_id,
        "principal_id": principal_id,
        "acl_terms": acl_terms,
        "query_embedding": query_vec,
        "model_version": "text-embedding-3-large",
        "top_k": 100,
    },
    timeout=0.5,
)
resp.raise_for_status()
candidates = resp.json()["results"]
```