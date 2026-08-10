# SIGNOFF_BLOCK_E

Canonical detailed record also in [SIGNOFF.md](SIGNOFF.md).


## Phase 2 Integration Signoff — Gemini Real Embedder (2026-08-09)

**Engineer:** Cursor Agent  
**Reviewer:** PENDING (section 24.1 independent review not claimed)  
**Provider:** Gemini `gemini-embedding-001` @ 768 dims (via `GEMINI_API_KEY`)  
**Fixtures:** Block Z v2 shared package (`FIXTURES_PATH=fixtures/`) for E2 corpus cycling  
**Auth:** JWT stub replaced with Block A RS256 public-key verification (`JWT_PUBLIC_KEY_PATH`)

| ID | Criterion | Phase 2 Result | Evidence |
|----|-----------|----------------|----------|
| E1 | Chunk integrity (AST) | **PASS** (re-run under Gemini env; chunker-only) | `pytest tests/test_block_e.py::test_E1_chunk_integrity` |
| E2 | Throughput >=500 docs/min/worker x 10 min | **PASS** — **1373.5 docs/min** aggregate; worst 60s window **1249.8**; throttle_events=0 | `evidence/e2_phase2_gemini_10min_results.json`, `evidence/e2_phase2_gemini_10min_console.txt` |
| E3 | Re-embed trigger | **PENDING** — Postgres `:5433` not available this session | — |
| E4 | Idempotent chunk IDs | **PASS** (re-run under Gemini env) | `pytest tests/test_block_e.py::test_E4_identical_chunk_ids_on_3_reprocess` |
| JWT | Real Block A signature validation | **PASS** — forged rejected; Block A-signed RS256 accepted | `tests/verify_jwt_block_a.py` |

**Phase 2 technical verdict:** E2 **PASS** against real Gemini. E1/E4 PASS. E3 not re-verified (infra). **Not Integration-signed** — reviewer PENDING.

### E2 reproduction command

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-e-chunking"
# Load GEMINI_API_KEY / EMBEDDING_MODEL / EMBEDDING_DIMENSION from backend\.env
$env:EMBEDDING_PROVIDER = "gemini"
$env:EMBEDDING_MODEL = "gemini-embedding-001"
$env:EMBEDDING_DIMENSION = "768"
$env:FIXTURES_PATH = "D:\PROJECTS\Sync Ai Final\fixtures"
$env:JWT_PUBLIC_KEY_PATH = "D:\PROJECTS\Sync Ai Final\backend\keys\public.pem"
$env:E2_DOC_CONCURRENCY = "4"
$env:E2_BATCH_SIZE = "50"
$env:GEMINI_MAX_BATCH_SIZE = "50"
$env:E2_DURATION_MINUTES = "10"
$env:PYTHONPATH = (Get-Location).Path
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" tests\run_e2_10min_test.py
```

### Deviation — Gemini instead of Azure OpenAI (dated 2026-08-09)

Architecture section 6.2 assumes Azure OpenAI embeddings as the production embedder (Azure-first stack: AKS, Azure AD, Block D Key Vault target). **This Phase 2 run used Google Gemini `gemini-embedding-001` (768-d) because `GEMINI_API_KEY` was available and Azure OpenAI credentials were empty.**

This is an **explicit interim deviation**, recorded the same way Block D recorded pgcrypto-vs-KMS: acceptable to unblock Integration evidence today, **not** the final production choice. Production should migrate to Azure OpenAI (or another architected provider) and re-run E2 before declaring production-ready embeddings. Downstream Block G indexes created from Gemini 768-d vectors are **not** interchangeable with Azure 1536/3072 spaces — re-embed required on provider switch.

### JWT fix notes

Block A does not expose a dedicated HTTP token-introspect route. Validation matches Blocks F/G/H/I/J: cryptographic verify against Block A's `keys/public.pem` (issuer `snyq-platform`, RS256). Optional `BLOCK_A_TOKEN_VALIDATE_URL` supported if an HTTP validate endpoint is added later. Stub unsigned decode removed from `app/api/v1/embed.py`.

### Fixture gap note

E2 used shared Block Z v2 `documents.json` (60 docs, cycled). E1 code-chunker verification still uses Block E private `fixtures/code/*` (Z v2 prose bodies lack multi-language AST code corpus).

---
