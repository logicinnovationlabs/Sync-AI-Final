# Block G — Independent Reviewer Verification Packet (G1–G4)

> **§24.1:** Independent human reviewer required. **Not** a signoff. See `services/block-g-vector-search/SIGNOFF.md`.

| Field | Value |
|-------|-------|
| Block | G — Vector Search |
| Engineer self-report | **Gemini 768 re-verification PASS** (2026-08-09 evening): G1–G4 all PASS after G2 ACL fix |
| Reviewer | **PENDING** — re-run independently |
| `fixtures_version` | **v2** |

Prior Phase 2 (2026-08-05) used **64-d synthetic** vectors. Integration evidence: real Gemini 768-d, collection prefix `block_g_verify_gemini`. G2 root cause was forbidden-list / ACL-entitlement mismatch (plus deny-override parity with Block F); see SIGNOFF “G2 ACL Fix” section.

---

## Isolation — Docker Compose

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-g-vector-search"
docker compose -f docker-compose.test.yml up -d
```

Qdrant on **:6335**.

---

## Required Environment Variables

| Variable | Placeholder |
|----------|-------------|
| `EMBEDDING_PROVIDER` | `gemini` |
| `EMBEDDING_MODEL` | `gemini-embedding-001` |
| `EMBEDDING_DIMENSION` | `768` |
| `GEMINI_API_KEY` | `<GEMINI_API_KEY>` |
| `FIXTURES_PATH` | `D:\PROJECTS\Sync Ai Final\fixtures` |
| `QDRANT_HOST` | `localhost` |
| `QDRANT_PORT` | `6335` |
| `G_REUSE_COLLECTION` | `1` (optional; reuse existing Gemini collection) |

---

## Reproduce

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-g-vector-search"
# load GEMINI_* into $env: without printing
$env:QDRANT_HOST="localhost"; $env:QDRANT_PORT="6335"
$env:FIXTURES_PATH="D:\PROJECTS\Sync Ai Final\fixtures"
$env:G_REUSE_COLLECTION="1"; $env:VECTOR_DB_TYPE="qdrant"
$env:EMBEDDING_PROVIDER="gemini"; $env:EMBEDDING_MODEL="gemini-embedding-001"
$env:EMBEDDING_DIMENSION="768"; $env:PYTHONPATH=(Get-Location).Path
& "..\..\.venv\Scripts\python.exe" tests\verify_g_gemini_reverification.py
```

Evidence: `evidence/g_gemini_g2fix_rerun_20260809.txt`, `evidence/g_gemini_reverification_20260809.json`, `evidence/g2_leak_diagnosis_20260809.txt`.

---

## Reviewer PASS/FAIL Table

| ID | Criterion | Engineer self-report | Reviewer PASS/FAIL | Evidence | Notes |
|----|-----------|---------------------|-------------------|----------|-------|
| G1 | Recall@10 ≥0.85 | PASS (1.0000) | | | |
| G2 | ACL prefilter zero leak | PASS (0/15) | | | After fixture+deny fix |
| G3 | Latency p95 ≤150 ms | PASS (~34.66 ms) | | | |
| G4 | Model-version handling | PASS | | | |

**Reviewer name / date / signature:** _______________
