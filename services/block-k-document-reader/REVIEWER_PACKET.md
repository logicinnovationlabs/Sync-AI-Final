# Block K — Independent Reviewer Verification Packet (K1–K3)

| Field | Value |
|-------|-------|
| Block | K — Document Reader Service |
| Engineer self-report | Phase 1 mock **PASS** (see SIGNOFF.md) |
| Reviewer | **PENDING** |
| API | `GET /api/v1/document/{id}` |

## Isolation

Phase 1: in-process `InMemoryDocumentStore` + `MockACLChecker` (pytest ASGI).  
Phase 2: `docker-compose.test.yml` (Postgres + MinIO + ACL mock) or real Block C/D/A.

## Reproduce — Phase 1 mock

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-k-document-reader"
$env:PYTHONPATH = (Get-Location).Path
$env:STORAGE_BACKEND = "mock"
$env:ACL_BACKEND = "mock"
$env:ENVIRONMENT = "test"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\ -v --tb=short -s
```

## Reproduce — Phase 2 compose deps

```powershell
cd "D:\PROJECTS\Sync Ai Final\services\block-k-document-reader"
docker compose -f docker-compose.test.yml up -d
$env:STORAGE_BACKEND = "minio"
$env:ACL_BACKEND = "http"
$env:STORAGE_ENDPOINT = "localhost:19000"
$env:STORAGE_ACCESS_KEY = "minioadmin"
$env:STORAGE_SECRET_KEY = "minioadmin"
$env:DB_URL = "postgresql://user:pass@localhost:15434/block_d"
$env:ACL_SERVICE_URL = "http://localhost:18001"
$env:ENVIRONMENT = "test"
$env:PYTHONPATH = (Get-Location).Path
# Seed documents table + MinIO objects, then:
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\ -v --tb=short
```

## Reviewer PASS/FAIL Table

| ID | Criterion | Engineer self-report | Reviewer PASS/FAIL | Evidence | Notes |
|----|-----------|---------------------|-------------------|----------|-------|
| K1 | ACL re-check, 100% post-revoke deny | PASS (Phase 1) | | | No ACL caching |
| K2 | Stream >10MB, bounded memory | PASS (Phase 1) | | | `X-Document-Streaming: 1` |
| K3 | Structure fidelity 100% | PASS (Phase 1) | | | Fixture `structured_document.json` |

**Reviewer name / date / signature:** _______________
