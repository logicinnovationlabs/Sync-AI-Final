# Block F: Lexical Search Service

Keyword retrieval with mandatory ACL prefiltering, BM25 ranking, faceting, and snippet generation.

## Quick start (Phase 1 — mock BM25)

```powershell
cd services/block-f-lexical-search
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
$env:ENVIRONMENT = "test"
$env:SEARCH_BACKEND = "mock"
python fixtures/generate_fixtures.py
python -m pytest tests/ -v -s --tb=short
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/search/lexical` | ACL-prefiltered lexical search |
| POST | `/_internal/index` | Index writer |
| GET | `/health` | Health |
| GET | `/search/metrics` | Latency / ACL metrics snapshot |

## Signoff criteria

| ID | Criterion | Threshold |
|----|-----------|-----------|
| F1 | Query latency | p95 ≤ 200ms |
| F2 | ACL enforcement | 0 unauthorized / 15 red-team cases |
| F3 | Index lag | p95 < 30s |
| F4 | Facet accuracy | 100% match |

See SIGNOFF.md and INTEGRATION_GUIDE.md.