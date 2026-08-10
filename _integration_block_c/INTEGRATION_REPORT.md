# Block C Integration Report — Sync-AI-Final (Pratham) → Synq-AI (Ishu)

**Date:** 2026-08-05  
**Status:** Partial integration complete — clean additions copied; conflicts / migrations / deps await human decision. **No commit. No push. No migrations applied.**

## Paths

| Role | Path |
|------|------|
| Target (Ishu working tree) | `D:\PROJECTS\Sync Ai Final` (branch `Ishu`, HEAD `ef818e7`) |
| Incoming (Pratham clone) | `D:\PROJECTS\Sync-AI-Final-Pratham` (branch `Pratham`, tip `75dff1e`) |
| Report artifacts | `D:\PROJECTS\Sync Ai Final\_integration_block_c\` |

Note: both trees point at the same GitHub remote (`logicinnovationlabs/Sync-AI-Final`) on different branches; integration was still done as a path-based, evidence-based copy (no `git merge`).

---

## 1. Backup (how to restore)

### A. Git branch (committed state only)
- **Branch:** `backup/pre-block-c-integration-20260805-045527`
- **Commit:** `ef818e7697d2364934605decff001d53f8997b75`
- **Restore committed tree:** `git -C "D:\PROJECTS\Sync Ai Final" checkout backup/pre-block-c-integration-20260805-045527`

### B. Timestamped working-tree copy (includes pre-integration dirty state)
- **Folder:** `D:\PROJECTS\Sync-Ai-Final-backup-pre-block-c-20260805-045527`
- **Contents:** full tree copy excluding `.git`, `node_modules`, `.venv`, `venv`, `__pycache__`, `.pytest_cache` (393 files)
- **Restore:** copy needed paths back from that folder, or delete the 44 added files listed in `copied_files.txt`

### C. Undo only the integration additions
Delete the 44 paths listed in `_integration_block_c\copied_files.txt` under `backend\`. No conflicted files were modified.

---

## 2. Inventory summary

| Tree | Scope | File count |
|------|-------|------------|
| Incoming | `Sync-AI-Final-Pratham/backend` | 166 |
| Target | `Sync Ai Final/backend` (pre-copy) | 148 |

### Comparison (by relative path under `backend/`)

| Category | Count | Artifact |
|----------|-------|----------|
| Clean additions (copied) | **44** | `clean_additions.txt` / `copied_files.txt` |
| Identical content (skipped) | **108** | `identical_skip.txt` |
| Conflicts (untouched) | **14** | `conflicts.txt` |

---

## 3. Files added (clean additions — all copied, hash-verified)

### Application code
- `app/acl/` — `__init__.py`, `compiler.py`, `container_service.py`, `inheritance.py`
- `app/api/v1/acl.py`, `app/api/v1/identity.py`
- `app/core/models.py`
- `app/identity/` — `__init__.py`, `models.py`, `resolver.py`, `matchers/*`
- `app/normalizer/` — base, mime_detector, ocr, registry, text_extractor, strategies/*
- `app/services/pipeline.py`
- `app/storage/canonical_repo.py`

### Tests and fixtures
- 12 new test modules under `tests/`
- `tests/fixtures/block_c/*.json` (4 fixtures)

### Docs / runners
- `BLOCK_C_SUMMARY.md`, `SIGNOFF_BLOCK_C.md`, `test-block-c.bat`

**Wiring caveat:** Neither incoming nor target `app/main.py` registers `acl` / `identity` routers. Copied API modules exist on disk but are **not mounted** until a human merges router wiring.

---

## 4. Conflicts (untouched — need human decision)

| File | What differs (short) |
|------|----------------------|
| `.env.example` | Incoming adds Block C env keys: `TESSERACT_PATH`, `OCR_LANGUAGE`, `OCR_TIMEOUT_SECONDS`, `MAX_EXTRACTED_CHARS`, `IDENTITY_CACHE_TTL`, `ACL_INHERITANCE_CACHE_TTL`, `ACL_REVALIDATION_INTERVAL_SECONDS`. |
| `app/core/config.py` | Target is **ahead**: has `supabase_db_url`, `jwt_active_kid` absent from incoming. Do **not** replace with Pratham. |
| `app/main.py` | Target includes `scoped_probes`; incoming does not. Neither wires `acl`/`identity` yet. Need additive merge. |
| `app/api/deps.py` | Target has A4 `require_matching_tenant()` + contracts errors; incoming is leaner. Keep target. |
| `app/middleware/tenant_middleware.py` | Target has soft-fail / logging hardening; incoming older. Keep target. |
| `app/services/token_service.py` | Target is larger; Ishu hardening. Keep target. |
| `app/workers/tasks.py` | Incoming adds `_get_pipeline()`, pipeline hooks, and `revalidate_acls_for_tenant` (~+168 lines). Needs careful manual merge. |
| `drive_service.py` | Incoming adds stub `fetch_permission_changes()` for ACL revalidation. Cherry-pick candidate. |
| `gmail_service.py` | Incoming adds stub `fetch_permission_changes()` returning `[]`. Cherry-pick candidate. |
| `requirements.txt` | Incoming-only OCR/doc packages — see deps section. **Do not auto-merge.** |
| `pyproject.toml` | Incoming `0.3.0` + Block C deps vs target `0.1.0`. **Do not auto-merge.** |
| `README.md` | Incoming much larger (Block C docs). Manual doc merge. |
| `SIGNOFF.md` | Target larger (Ishu closeout). Keep target; use added `SIGNOFF_BLOCK_C.md`. |
| `tests/test_signoff.py` | Incoming adds SEC_A8–A22 / EDGE_A23–A26 tests absent from target. Separate decision. |

---

## 5. Migrations / shared infrastructure (flagged — NOT executed)

| Item | Status |
|------|--------|
| `migrations/versions/000_*.py`, `001_*.py` | **Identical** in both trees — no action |
| New alembic revisions in clean additions | **None** |
| docker-compose / Dockerfiles | **Identical** — no action |
| CanonicalDocument / ACLEntry Postgres schema | **Not shipped as migrations.** `CanonicalRepo` is in-memory; docs say SQLAlchemy wiring is future work. |
| Qdrant / Redis changes in additions | **None.** Docs mention future ACL filtering in Qdrant (Block G). |

**No migration was run against any database.**

---

## 6. Dependency mismatches (not resolved)

Packages present in **both** with **different** version pins: **none**.

Packages **incoming-only** (needed for Block C; not installed):

- `beautifulsoup4==4.12.0`
- `openpyxl==3.1.0`
- `pdfplumber==0.10.3`
- `pillow==10.0.0`
- `pytesseract==0.3.10`
- `python-docx==1.1.0`
- `python-magic-bin==0.4.14`
- `python-pptx==0.6.21`

`pyproject.toml` carries the same incoming-only set plus version metadata conflict (`0.3.0` vs `0.1.0`). Manifests were **not** modified.

---

## 7. Test results

Runner: Docker image `backend-test:latest` with target `app/` + `tests/` mounted.

### Before copy
`2 failed, 35 passed, 180 warnings, 12 errors`  
(Pre-existing: many tests dial `127.0.0.1:5432` from inside the container.)

### After copy — full `pytest tests/`
**Collection interrupted:** 5 import errors on new Block C tests (`ModuleNotFoundError: magic`, `PIL`) because Block C deps were not installed (manifests untouched by design).

### After copy — comparable pre-existing suite only
`2 failed, 35 passed, 180 warnings, 12 errors` — **identical to before**.

**Verdict:** No regression on the previously runnable suite. Full-suite collection fails until Block C deps are deliberately approved/installed.

---

## 8. Recommended next human decisions (priority)

1. Cherry-pick additive `fetch_permission_changes` stubs into Drive/Gmail connectors.
2. Manually merge pipeline + `revalidate_acls_for_tenant` into target `app/workers/tasks.py`.
3. Add Block C env keys to `.env.example` / `config.py` without dropping Ishu fields.
4. Wire `acl` + `identity` routers in `main.py` while keeping `scoped_probes`.
5. Approve adding the 8 incoming-only packages and rebuild `backend-test`, then run Block C tests.
6. Decide later on Postgres persistence for `CanonicalRepo` (new migration — separate approval).
7. Do **not** replace `deps.py`, `tenant_middleware.py`, `token_service.py`, or `SIGNOFF.md` with Pratham versions.

---

## 9. Process constraints confirmation

- No conflict file overwritten or deleted
- No dependency manifest silently changed
- No migration / alembic upgrade executed
- No commit / push
- No force operations
- Backup branch + timestamped copy created before copies
- Only clean-addition paths written under `backend/` (plus `_integration_block_c/` report folder)
