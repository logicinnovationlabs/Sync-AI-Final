# Block A — Independent Reviewer Verification Packet (A1–A5)

> **§24.1:** An independent human reviewer must execute this packet and record PASS/FAIL. This document is **not** a signoff and does not replace `backend/SIGNOFF.md`.

| Field | Value |
|-------|-------|
| Block | A — Tenancy, Identity, Auth (`backend/`) |
| Engineer self-report | A1–A5 **PASS** |
| Reviewer | **PENDING** |
| `fixtures_version` | **v2.1** |

---

## Isolation — Docker Compose

```powershell
cd "D:\PROJECTS\Sync Ai Final\backend"
docker compose -f docker-compose.yml up -d redis
```

A1–A5 uses verify Postgres `block-a-verify-pg` on **:5434** (manual — matches SIGNOFF):

```powershell
docker run -d --name block-a-verify-pg -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=verify -e POSTGRES_DB=block_a_verify -p 5434:5432 postgres:16
```

---

## Required Environment Variables

| Variable | Placeholder / example |
|----------|----------------------|
| `SNYQ_IGNORE_ENV_FILE` | `1` |
| `JWT_PRIVATE_KEY_PATH` | `D:\PROJECTS\Sync Ai Final\backend\keys\private.pem` |
| `JWT_PUBLIC_KEY_PATH` | `D:\PROJECTS\Sync Ai Final\backend\keys\public.pem` |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://postgres:verify@localhost:5434/block_a_verify` |
| `CONTROL_PLANE_DATABASE_URL` | same as above |
| `REDIS_URL` | `redis://localhost:6379` |

Do not print key material or `.env` secrets.

---

## Reproduce Criteria (from `backend/SIGNOFF.md`)

```powershell
cd "D:\PROJECTS\Sync Ai Final\backend"
$env:SNYQ_IGNORE_ENV_FILE = "1"
$env:JWT_PRIVATE_KEY_PATH = "D:\PROJECTS\Sync Ai Final\backend\keys\private.pem"
$env:JWT_PUBLIC_KEY_PATH = "D:\PROJECTS\Sync Ai Final\backend\keys\public.pem"
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:verify@localhost:5434/block_a_verify"
$env:CONTROL_PLANE_DATABASE_URL = "postgresql+asyncpg://postgres:verify@localhost:5434/block_a_verify"
$env:REDIS_URL = "redis://localhost:6379"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_signoff_closeout_local.py -v -s
```

| ID | Pass threshold |
|----|----------------|
| A1 | 100/100 tokens with exactly one `tenant_id` |
| A2 | 20/20 revocations within ≤60s |
| A3 | Identical `principal_id` across 3 process restarts |
| A4 | 50/50 cross-tenant attempts rejected |
| A5 | 7/7 scoped routes return 403 envelope |

---

## Reviewer PASS/FAIL Table

| ID | Criterion | Engineer self-report | Reviewer PASS/FAIL | Evidence | Notes |
|----|-----------|---------------------|-------------------|----------|-------|
| A1 | Tenant binding integrity | PASS | | | |
| A2 | Revocation latency | PASS | | | |
| A3 | SCIM idempotency | PASS | | | |
| A4 | Cross-tenant replay rejection | PASS | | | |
| A5 | Scope enforcement | PASS | | | |

**Reviewer name / date / signature:** _______________
