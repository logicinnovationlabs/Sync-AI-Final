# Block K: Document Reader Service – Signoff

Per architecture document (Glean_Arch_made_by_Glean_v1_3) and Block K master prompt.

## Phase 1 (Provisional) – against Block Z / in-process mocks

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| K1 | ACL re-check (no cache after revoke) | PASS | `tests/test_k1_acl_recheck.py` |
| K2 | Streaming >10MB, memory bounded | PASS | `tests/test_k2_streaming.py` |
| K3 | Structure fidelity (headings/tables/code) | PASS | `tests/test_k3_structure.py` |

Latest Phase 1 run: **2026-08-11** — 7 passed (`evidence/phase1_pytest_20260811.txt`).

## Phase 2 (Integration) – Postgres + MinIO + ACL mock (compose)

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| K1 | ACL re-check | PASS | allow=200, deny_b=403, post-revoke 10/10 (`evidence/k_phase2_20260811.json`) |
| K2 | Streaming >10MB | PASS | streaming=True, body_len=10551296, gen_growth=183883 |
| K3 | Structure fidelity | PASS | structure/body/title 100% match |

Latest Phase 2 run: **2026-08-11** — OVERALL PASS against:
- Postgres `localhost:15434` (`block-k-postgres-test`)
- MinIO `localhost:19000` (`block-k-minio-test`)
- ACL mock `localhost:18001` (`block-k-acl-mock`)

### Reproduce Phase 2

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-k-document-reader"
docker compose -f docker-compose.test.yml up -d
$env:DB_URL = "postgresql://user:pass@localhost:15434/block_d"
$env:STORAGE_ENDPOINT = "localhost:19000"
$env:STORAGE_ACCESS_KEY = "minioadmin"
$env:STORAGE_SECRET_KEY = "minioadmin"
$env:STORAGE_BUCKET = "documents"
$env:ACL_SERVICE_URL = "http://localhost:18001"
$env:STORAGE_BACKEND = "minio"
$env:ACL_BACKEND = "http"
..\..\.venv\Scripts\python.exe scripts\seed_phase2.py
..\..\.venv\Scripts\python.exe scripts\verify_k_phase2.py
```

**Block signoff: PASS** (Phase 1 + Phase 2).

Independent reviewer: **PENDING**.