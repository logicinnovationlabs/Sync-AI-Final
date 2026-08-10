# Block E — Independent Reviewer Verification Packet (E1–E6)

> **§24.1:** Independent human reviewer required. **Not** a signoff. See `services/block-e-chunking/SIGNOFF.md`.

| Field | Value |
|-------|-------|
| Block | E — Chunking and Embedding |
| Engineer self-report | E1–E6 **PASS** (Gemini Phase 2 deviation 2026-08-09) |
| Reviewer | **PENDING** |
| `fixtures_version` | **v2.1** |

**Notes:** E1 prefers `FIXTURES_PATH/code_corpus`; private `fixtures/code/` is fallback. E2 used Gemini interim (not Azure OpenAI).

---

## Isolation — Docker Compose

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-e-chunking"
docker compose -f docker-compose.yml up -d --build
```

---

## Required Environment Variables

| Variable | Placeholder |
|----------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:verify@localhost:5433/block_e_verify` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` |
| `EMBEDDING_PROVIDER` | `gemini` |
| `EMBEDDING_MODEL` | `gemini-embedding-001` |
| `EMBEDDING_DIMENSION` | `768` |
| `GEMINI_API_KEY` | `<GEMINI_API_KEY>` |
| `FIXTURES_PATH` | `D:\PROJECTS\Sync Ai Final\fixtures` |
| `JWT_PUBLIC_KEY_PATH` | `D:\PROJECTS\Sync Ai Final\backend\keys\public.pem` |

---

## Reproduce Criteria (from `SIGNOFF.md`)

### E1

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-e-chunking"
$env:FIXTURES_PATH = "D:\PROJECTS\Sync Ai Final\fixtures"
$env:PYTHONPATH = (Get-Location).Path
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_block_e.py::test_E1_chunk_integrity -v
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" tests\verify_component4_code_chunker.py
```

### E2 (Phase 2 Gemini, 10 min)

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-e-chunking"
$env:EMBEDDING_PROVIDER = "gemini"
$env:EMBEDDING_MODEL = "gemini-embedding-001"
$env:EMBEDDING_DIMENSION = "768"
$env:FIXTURES_PATH = "D:\PROJECTS\Sync Ai Final\fixtures"
$env:JWT_PUBLIC_KEY_PATH = "D:\PROJECTS\Sync Ai Final\backend\keys\public.pem"
$env:E2_DOC_CONCURRENCY = "4"
$env:E2_BATCH_SIZE = "50"
$env:GEMINI_MAX_BATCH_SIZE = "50"
$env:E2_DURATION_MINUTES = "10"
$env:GEMINI_API_KEY = "<GEMINI_API_KEY>"
$env:PYTHONPATH = (Get-Location).Path
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" tests\run_e2_10min_test.py
```

### E3 / E4 / E5 / E6

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-e-chunking"
docker compose -f docker-compose.yml up -d
$env:DATABASE_URL = "postgresql+asyncpg://postgres:verify@localhost:5433/block_e_verify"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:CELERY_BROKER_URL = "redis://localhost:6379/1"
$env:CELERY_RESULT_BACKEND = "redis://localhost:6379/2"
$env:PYTHONPATH = (Get-Location).Path
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" tests\verify_e3_10k_reembed.py
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" tests\verify_e4_idempotency.py
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" tests\verify_e5_write_verification.py
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" tests\verify_component5_tenant_isolation.py
```

---

## Reviewer PASS/FAIL Table

| ID | Criterion | Engineer self-report | Reviewer PASS/FAIL | Evidence | Notes |
|----|-----------|---------------------|-------------------|----------|-------|
| E1 | Chunk integrity (AST) | PASS | | | shared `code_corpus/` |
| E2 | Throughput ≥500 docs/min | PASS (Gemini) | | | interim provider |
| E3 | Re-embed trigger (10k) | PASS | | | |
| E4 | Idempotent chunk IDs | PASS | | | |
| E5 | Write-path correctness | PASS | | | |
| E6 | Tenant isolation | PASS | | | |

**Reviewer name / date / signature:** _______________
