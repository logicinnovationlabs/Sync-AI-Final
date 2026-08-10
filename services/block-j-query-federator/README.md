# Block J: Query Federator and Ranking Service

Orchestrates hybrid enterprise search: fans out to Blocks F (lexical), G (vector),
and H (graph), merges candidates, applies an ACL post-check, ranks with fusion +
optional cross-encoder reranking, and returns permission-safe results.

## Quick start (Phase 1 — mock backends)

```powershell
cd services/block-j-query-federator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
$env:PYTHONPATH = (Get-Location).Path
python fixtures/generate_fixtures.py
python -m pytest tests/ -v --tb=short -s
```

Run the API against in-process mock F/G/H:

```powershell
# Terminal 1 — mock backends (F/G/H compatible routes)
$env:PYTHONPATH = (Get-Location).Path
uvicorn mocks.backend_server:mock_app --port 8090

# Terminal 2 — federator
$env:PYTHONPATH = (Get-Location).Path
$env:LEXICAL_SEARCH_URL = "http://localhost:8090"
$env:VECTOR_SEARCH_URL = "http://localhost:8090"
$env:GRAPH_SERVICE_URL = "http://localhost:8090"
$env:ACL_BACKEND = "memory"
$env:RERANKER_BACKEND = "mock"
uvicorn app.main:app --port 8089 --reload
```

Example search:

```powershell
# Build a test JWT (tenant_j_test / user:alice)
python -c "import base64,json; h=base64.urlsafe_b64encode(b'{\"alg\":\"none\"}').rstrip(b'=').decode(); p=base64.urlsafe_b64encode(json.dumps({'tenant_id':'tenant_j_test','principal_id':'user:alice','groups':['group:eng'],'scopes':['search.read']}).encode()).rstrip(b'=').decode(); print(f'{h}.{p}.x')"

curl -X POST http://localhost:8089/api/v1/search -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d "{\"query\":\"How does kubernetes work?\",\"size\":5}"
```

## Docker Compose

```powershell
docker compose up --build
```

- Federator: `http://localhost:8089`
- Mock backends: `http://localhost:8090`
- Optional Postgres (ACL): `localhost:5439`

Before serving with mocks, load fixtures into the mock process (tests do this
automatically). For compose, regenerate fixtures and mount `fixtures/`.

## Environment variables

See `.env.example`. Important keys:

| Variable | Default | Purpose |
|----------|---------|---------|
| `LEXICAL_SEARCH_URL` | `http://localhost:8086` | Block F |
| `VECTOR_SEARCH_URL` | `http://localhost:8087` | Block G |
| `GRAPH_SERVICE_URL` | `http://localhost:8088` | Block H |
| `BACKEND_TIMEOUT_SECONDS` | `0.4` | Per-backend timeout |
| `LEXICAL_WEIGHT` / `VECTOR_WEIGHT` / `GRAPH_WEIGHT` | 0.4 / 0.4 / 0.2 | Fusion |
| `RERANKER_BACKEND` | `mock` | `mock` or `cross_encoder` |
| `RERANKER_MODEL_NAME` | `BAAI/bge-reranker-v2-m3` | Cross-encoder id |
| `ACL_BACKEND` | `memory` | `memory` or `postgres` |
| `DATABASE_URL` | postgres URL | Used when `ACL_BACKEND=postgres` |
| `EMBEDDING_BACKEND` | `mock` | `mock` or `openai` |

### Cross-encoder (production ranking)

```powershell
pip install sentence-transformers torch
$env:RERANKER_BACKEND = "cross_encoder"
$env:RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
```

The model loads once at startup.

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/search` | Federated hybrid search (internal) |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus text metrics |

Request body:

```json
{
  "query": "How does kubernetes work?",
  "tenant_id": "tenant_j_test",
  "size": 20,
  "from": 0,
  "facets": ["source", "object_type"]
}
```

Auth: Block A JWT bearer. Claims used: `tenant_id`, `principal_id` (or `user_id`),
`groups`, `scopes`, optional `acl_terms`.

## Signoff criteria (architecture §24)

| ID | Criterion | Threshold |
|----|-----------|-----------|
| J1 | 100 federated queries latency | p95 ≤ 800 ms |
| J2 | 15 red-team cases × backend combos | 0 unauthorized |
| J3 | 30 labeled queries | NDCG@10 ≥ 0.80 |
| J4 | Kill G, then H independently | valid partial results, 0 5xx |

Run signoff:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python fixtures/generate_fixtures.py
python -m pytest tests/test_federator.py tests/test_ranker.py tests/test_permission.py -v --tb=short -s
```

Interpret results:

- **J1**: printed `J1 p95 latency: …` must be ≤ 800.
- **J2**: assertion fails if any forbidden doc id appears for any backend combo.
- **J3**: printed average NDCG@10 must be ≥ 0.80.
- **J4**: no exceptions when vector or graph mocks are killed.

Fixtures live under `fixtures/` (Block-Z-shaped; regenerate with
`python fixtures/generate_fixtures.py`). Override path with `FIXTURES_PATH`.

## Architecture flow

```
Client → POST /api/v1/search
       → JWT → UserContext
       → asyncio.gather(lexical, vector)
       → merge/dedupe by document_id
       → ACL post-check (acl_entries batch)
       → graph signals (optional)
       → fusion + rerank
       → paginate + facets/citations
```

Graceful degradation: each backend call is isolated. If one fails, others
continue. Only when **both** lexical and vector fail does the API return 500.

## Project layout

```
app/           FastAPI service (config, models, clients, services, auth, utils)
mocks/         Block F/G/H compatible mock server for local/signoff
fixtures/      Corpus, ACL, red-team, relevance, latency queries
tests/         Unit + J1–J4 integration tests
Dockerfile
docker-compose.yml
requirements.txt
```
