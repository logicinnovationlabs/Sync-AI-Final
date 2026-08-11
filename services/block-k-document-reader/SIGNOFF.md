# Block K: Document Reader Service – Signoff

Per architecture document (Glean_Arch_made_by_Glean_v1_3) and Block K master prompt.

## Phase 1 (Provisional) – against Block Z / in-process mocks

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| K1 | ACL re-check (no cache after revoke) | PASS | `tests/test_k1_acl_recheck.py` |
| K2 | Streaming >10MB, memory bounded | PASS | `tests/test_k2_streaming.py` |
| K3 | Structure fidelity (headings/tables/code) | PASS | `tests/test_k3_structure.py` |

Run:

```powershell
cd services\block-k-document-reader
$env:PYTHONPATH = (Get-Location).Path
$env:STORAGE_BACKEND = "mock"
$env:ACL_BACKEND = "mock"
$env:ENVIRONMENT = "test"
..\..\.venv\Scripts\python.exe -m pytest tests\ -v --tb=short
```

## Phase 2 (Integration) – against real Block C, D, A

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| K1 | ACL re-check | PENDING | Requires live Block C `/acl/compile` |
| K2 | Streaming | PENDING | Requires live Block D MinIO + Postgres |
| K3 | Structure fidelity | PENDING | Requires structured docs in Block D |

Block signoff: **PASS** only if all criteria PASS in both phases.

Latest Phase 1 run: **2026-08-11 06:32 UTC** — 7 passed (see evidence/phase1_pytest_20260811.txt).

Independent reviewer: **PENDING**.
