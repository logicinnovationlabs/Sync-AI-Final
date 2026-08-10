# Block Z — Independent Reviewer Verification Packet (Z1–Z3)

> **§24.1:** An independent human reviewer must execute this packet and record PASS/FAIL. This document is **not** a signoff and does not replace `fixtures/SIGNOFF_BLOCK_Z.md`.

| Field | Value |
|-------|-------|
| Block | Z — Shared Fixtures & Contracts |
| Engineer self-report | Z1–Z3 **PASS** (provisional; formal signoff **NOT CLAIMED**) |
| Reviewer | **PENDING** |
| `fixtures_version` | **v2.1** (MANIFEST includes `code_corpus/`, 36 files) |

---

## Isolation — Docker Compose

Block Z has **no block-local docker-compose**. Verification runs at repo root.

Optional contract mock (root `docker-compose.test.yml`):

```powershell
cd "D:\PROJECTS\Sync Ai Final"
docker compose -f docker-compose.test.yml up -d mock-server
```

---

## Required Environment Variables

No secrets required for Z1–Z3.

| Variable | Example | Purpose |
|----------|---------|---------|
| `FIXTURES_PATH` | `D:\PROJECTS\Sync Ai Final\fixtures` | Fixture root override |
| `CONTRACTS_PATH` | `D:\PROJECTS\Sync Ai Final\contracts` | OpenAPI contract root |

---

## Reproduce Criteria (from `fixtures/SIGNOFF_BLOCK_Z.md`)

### Regenerate fixtures (optional)

```powershell
cd "D:\PROJECTS\Sync Ai Final"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" fixtures\generate_fixtures.py
```

### Z1 — Contracts present and parseable

```powershell
cd "D:\PROJECTS\Sync Ai Final"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m tests.helpers.fixture_linter --fixtures fixtures
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_block_z.py tests\test_blocks\test_block_z.py -v
```

**Pass threshold (Z1):** ≥10 OpenAPI contracts; 0 schema violations.

### Z2 — Fixture lint + version alignment

**Pass threshold (Z2):** documents=60, principals=25, groups=10, errors=0; MANIFEST **v2.1**.

### Z3 — Swap shape normalization

**Pass threshold (Z3):** Normalized lexical-search shapes stable.

### Downstream smoke (2026-08-08 reference)

```powershell
cd "D:\PROJECTS\Sync Ai Final"
& "D:\PROJECTS\Sync Ai Final\.venv\Scripts\python.exe" -m pytest tests\test_block_c.py tests\test_block_f.py tests\test_block_g.py tests\test_block_h.py tests\test_block_j.py -v
```

---

## Reviewer PASS/FAIL Table

| ID | Criterion | Engineer self-report | Reviewer PASS/FAIL | Evidence | Notes |
|----|-----------|---------------------|-------------------|----------|-------|
| Z1 | Contracts present and parseable | PASS | | | |
| Z2 | Fixture lint + MANIFEST v2 alignment | PASS | | | directory fixtures (code_corpus/) allowed |
| Z3 | Mock shape normalization / swap readiness | PASS | | | |

**Reviewer name / date / signature:** _______________
