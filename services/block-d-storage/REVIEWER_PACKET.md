# Block D — Independent Reviewer Verification Packet (D1–D4)

> **§24.1:** Independent human reviewer required. **Not** a signoff. See `services/block-d-storage/SIGNOFF.md`.

| Field | Value |
|-------|-------|
| Block | D — Storage Substrate |
| Engineer self-report | D1–D4 **PASS** (Phase 2 Postgres + MinIO) |
| Reviewer | **PENDING** |
| `fixtures_version` | **v2.1** |

---

## Isolation — Docker Compose

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-d-storage"
docker compose -f docker-compose.yml up -d
docker exec block-d-verify-pg psql -U postgres -d block_d_verify -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

---

## Required Environment Variables

| Variable | Value |
|----------|-------|
| Postgres | `postgresql://postgres:verify@localhost:5435/block_d_verify` |
| MinIO | `localhost:9000`, keys `minioadmin` / `minioadmin` |

---

## Reproduce Criteria (from `SIGNOFF.md`)

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-d-storage"
$env:PYTHONPATH = (Get-Location).Path
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_block_d.py -v -s
```

Individual Phase 2 scripts:

```powershell
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_D1_provisioning_time_local.py -v -s
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_D2_backup_restore_local.py -v -s
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_D3_storage_isolation_local.py -v -s
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_D4_key_rotation_local.py -v -s
```

| ID | Pass threshold |
|----|----------------|
| D1 | 10 tenants in <300s |
| D2 | Row/object checksums match pre-backup |
| D3 | 20/20 cross-tenant reads blocked |
| D4 | Zero downtime rotation, zero data loss |

---

## Reviewer PASS/FAIL Table

| ID | Criterion | Engineer self-report | Reviewer PASS/FAIL | Evidence | Notes |
|----|-----------|---------------------|-------------------|----------|-------|
| D1 | Provisioning time | PASS | | | |
| D2 | Backup/restore integrity | PASS | | | |
| D3 | Storage-layer tenant isolation | PASS | | | |
| D4 | Key rotation | PASS | | | |

**Reviewer name / date / signature:** _______________
