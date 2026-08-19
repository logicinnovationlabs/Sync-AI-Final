# Fix Pass — Blocks D, E, G

**Repo:** `logicinnovationlabs/Sync-AI-Final`  
**Branch:** `Pratham` (`5ce77b1 Add: Block N completed and tested`)  
**Date:** 2026-08-16  
**Mode:** Fix, scoped to the §2 list. No commit, no push, `SIGNOFF.md` not touched.

`.bak` was taken with `Copy-Item` before every existing file edit. `*.bak` is gitignored; copies remain on disk next to the originals.

---

## 6.1 Per fix

### D-fix-1 — `EncryptionClient` constructor / `tests/test_encryption.py`

**Files changed:** `services/block-d-storage/tests/test_encryption.py`  
**`.bak`:** `services/block-d-storage/tests/test_encryption.py.bak`

**Root cause (differs from a “make vault optional” guess):** the constructor is correct. Real non-test callers pass both `db_client` and `vault_client`:

- `verify_component2_encrypt_decrypt.py`
- `verify_component3_key_rotation.py`
- `tests/test_D4_key_rotation_local.py`
- `tests/test_D4_key_rotation.py`
- `backend/tests/test_block_d_signoff.py` (`EncryptionClient(None, vault_client)`)

`EncryptionClient.__init__(self, db_client, vault_client)` was left required. The test was stale: it constructed `EncryptionClient(mock_db)` and expected `RuntimeError` matching `pgsodium`. The live client verifies **pgcrypto** (`SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto'`).

**Second instance of the same one-arg construction (not fixed here):** `services/block-d-storage/verify_component1_key_creation.py` still does `EncryptionClient(db_client)`. Flagged only; constructor was not loosened.

**Change:** tests now pass `MockVaultClient()` from `tests/mocks.py` and expect `RuntimeError` matching `pgcrypto extension is not enabled`.

**Re-run:**

```
$env:PYTHONPATH = "D:\PROJECTS\A sync Ai final\services\block-d-storage"
python -m pytest tests/test_encryption.py -v --tb=short
```

```
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\python.exe
cachedir: .pytest_cache
rootdir: D:\PROJECTS\A sync Ai final
configfile: pytest.ini
plugins: anyio-4.14.1, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 4 items

tests\test_encryption.py::TestEncryptionClient::test_pgsodium_verification_fails_without_extension PASSED [ 25%]
tests\test_encryption.py::TestEncryptionClient::test_encrypt_requires_pgsodium PASSED [ 50%]
tests\test_encryption.py::TestEncryptionClient::test_decrypt_requires_pgsodium PASSED [ 75%]
tests\test_encryption.py::TestEncryptionClient::test_rotate_key_requires_pgsodium PASSED [100%]

============================== 4 passed in 0.04s ==============================
```

**Result:** **PASS**

---

### D-fix-2 — MinIO `InvalidAccessKeyId` (D2)

**Files changed:** `services/block-d-storage/tests/test_D2_backup_restore_local.py`  
**`.bak`:** `services/block-d-storage/tests/test_D2_backup_restore_local.py.bak`

**Root cause (differs from “env-var name mismatch”):** compose credential **names** already match what MinIO expects (`MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`). The D2 test did not read those env vars. It hard-coded S3 keys `verify` / `verifyverify` into boto3, while this block’s compose sets `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` to `minioadmin`/`minioadmin`. Compose names were not changed.

**Change:** test constants `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` set to `minioadmin` / `minioadmin` to match the compose MinIO service. Backup/restore client code was not using a different env-var name.

**Re-run** against running `block-d-verify-minio` (`localhost:9000`) and `block-d-verify-pg` (`localhost:5435`):

```
$env:PYTHONPATH = "D:\PROJECTS\A sync Ai final\services\block-d-storage"
python -m pytest tests/test_D2_backup_restore_local.py -v --tb=short -s
```

```
tests\test_D2_backup_restore_local.py::TestD2BackupRestoreLocal::test_D2_backup_restore_integrity_local
D2 Test Configuration:
  Database host: localhost
  Database port: 5435
  Database name: block_d_verify
  Connection loaded: True

D2: Setting up tables...
D2: Tables created/verified

D2 Test Tenant Setup:
  Creating tenant: d2_test_tenant
  Creating test table with sample data
  Initial row count: 100
  Pre-backup checksum: ec0aaddc362433a74cd742162a06bc8c88063b6e882d47a995242efffa6c3666

D2 Backup/Restore Integrity Test (Local Postgres + MinIO):
  Tenant ID: d2_test_tenant
  Schema: tenant_d2_test_tenant
  Initial row count: 100
  Pre-backup checksum: ec0aaddc362433a74cd742162a06bc8c88063b6e882d47a995242efffa6c3666
  Initial object count: 10
  Pre-backup object checksum: 96a6a53091b7c616c5a3fedb6cd4b3fe46412f7259a1fed004561c29148a79dd

  Step 1: Backing up tenant schema...
    Backup ID: backup_d2_test_tenant_20260816_152320_102069
    Backup row count: 100
    Backup checksum: 4f11948f2488ee1ed4456afec3acc5a1df7dc3a94bfaeb5c54a1a5b4f373aa21

  Step 2: Dropping schema and deleting objects...
    Schema dropped
    Objects deleted; remaining under prefix: 0

  Step 3: Restoring tenant schema and objects...
    Restore tenant ID: d2_test_tenant
    Restore schema: tenant_d2_test_tenant
    Restore row count: 100

  Step 4: Verifying post-restore row count...
    Post-restore row count: 100

  Step 5: Verifying post-restore DB checksum...
    Post-restore DB checksum: ec0aaddc362433a74cd742162a06bc8c88063b6e882d47a995242efffa6c3666

  Step 6: Verifying post-restore object count and checksum...
    Post-restore object count: 10
    Post-restore object checksum: 96a6a53091b7c616c5a3fedb6cd4b3fe46412f7259a1fed004561c29148a79dd

D2 Backup/Restore Integrity Test Results:
  Initial row count: 100
  Backup row count: 100
  Restored row count: 100
  Pre-backup DB checksum: ec0aaddc362433a74cd742162a06bc8c88063b6e882d47a995242efffa6c3666
  Post-restore DB checksum: ec0aaddc362433a74cd742162a06bc8c88063b6e882d47a995242efffa6c3666
  Initial object count: 10
  Restored object count: 10
  Pre-backup object checksum: 96a6a53091b7c616c5a3fedb6cd4b3fe46412f7259a1fed004561c29148a79dd
  Post-restore object checksum: 96a6a53091b7c616c5a3fedb6cd4b3fe46412f7259a1fed004561c29148a79dd
  DB checksums match: True
  Object checksums match: True
  D2 PASSED: Row/object counts and checksums match pre-backup state exactly
PASSED

============================== 1 passed in 1.76s ==============================
```

**Result:** **PASS**

---

### D-fix-3 — `pgcrypto` (D4)

See **§6.2**. Local-fixable (Block D compose Postgres on `:5435`), not hosted Supabase.

**Files changed:**

- `services/block-d-storage/migrations/001_create_tenants_table.sql` (`.bak` taken)
- `services/block-d-storage/docker-compose.yml` (`.bak` taken) — mount `./initdb` → `/docker-entrypoint-initdb.d`
- `services/block-d-storage/initdb/01_pgcrypto.sql` (new)
- `services/block-d-storage/tests/test_D4_key_rotation_local.py` (`.bak` taken) — `CREATE EXTENSION IF NOT EXISTS pgcrypto` in `d4_schema_setup` so the already-initialized volume gets the extension without deleting data

**Root cause:** D4 local test targets `postgresql://postgres:verify@localhost:5435/block_d_verify` (this block’s own compose). The database did not have `pgcrypto` enabled. Init scripts on an existing volume do not re-run; the fixture `CREATE EXTENSION` is what made this re-run pass.

**Re-run:**

```
$env:PYTHONPATH = "D:\PROJECTS\A sync Ai final\services\block-d-storage"
python -m pytest tests/test_D4_key_rotation_local.py -v --tb=short -s
```

```
tests\test_D4_key_rotation_local.py::TestD4KeyRotationLocal::test_D4_key_rotation_with_load
D4 Test Configuration:
  Database host: localhost
  Database port: 5435
  Database name: block_d_verify
  Connection loaded: True

D4 Schema Setup:
  Creating isolated schema: d4_test
  Schema and table created successfully

D4 Key Rotation Test (Local Postgres):
  Isolation: Using dedicated schema d4_test
  Load pattern: 10 concurrent workers, 70% reads / 30% writes
  Duration: 5s stabilization + rotation + 10s post-rotation

  Creating pgcrypto keys...
  Old key created: key_id=d4_test_old_key_1786893808, name=d4_test_old_key_1786893808

  Starting concurrent load generation...
  Stabilizing load for 5 seconds...

  Triggering key rotation...
  New key created: key_id=d4_test_new_key_1786893808, name=d4_test_new_key_1786893808
  Key rotation completed in 0.006s
  Continuing load for 10 seconds post-rotation...

D4 Key Rotation Test Results:
  Total requests: 10981
  Successful requests: 10981
  Failed requests: 0
  Read requests: 7686
  Write requests: 3295
  Failed during rotation: 0
  Rotation duration: 0.006s
  Average latency: 0.01ms

  Verifying pre-rotation data decrypts correctly...
  Pre-rotation decryption: 8/8 successful
  D4 PASSED: Zero downtime, zero data loss, all pre-rotation data decrypts correctly
PASSED

============================= 1 passed in 16.81s ==============================
```

**Result:** **PASS**

---

### E-fix-1 — Test-collection hygiene

**Files changed:** relocated `services/block-e-chunking/tests/test_container_db_connection.py` → `services/block-e-chunking/scripts/check_container_db_connection.py` (not deleted).  
**`.bak`:** `services/block-e-chunking/tests/test_container_db_connection.py.bak`

**Root cause:** module-level `psycopg2.connect(...)` + `sys.exit(1)` ran at pytest collection. Host `postgres` from Windows resolved to public addresses and timed out, aborting the whole `tests/` directory (exit 3).

**Change:** moved out of `tests/` to `scripts/check_container_db_connection.py` (no `test_` prefix). Functionality preserved.

**Re-run — collection (no SystemExit):**

```
python -m pytest tests/ --collect-only -q
```

```
tests/test_block_e.py::test_E1_chunk_integrity
tests/test_block_e.py::test_E2_structural_throughput
tests/test_block_e.py::test_E3_reembed_triggered
tests/test_block_e.py::test_E4_identical_chunk_ids_on_3_reprocess

4 tests collected in 0.93s
EXITCODE=0
```

**Re-run — script on its own (host):** expected fail; hostname `postgres` is a Docker DNS name, not reachable from Windows.

```
python scripts/check_container_db_connection.py
HOST_EXIT=1
```

```
Testing connection to: postgresql://postgres:postgres@postgres:5432/block_e
Connection failed: connection to server at "postgres" (207.207.210.107), port 5432 failed: Connection timed out
```

**Re-run — same script inside `block-e-chunking-celery-worker-1` (where `postgres` is the compose service):**

```
DOCKER_EXIT=0
Testing connection to: postgresql://postgres:postgres@postgres:5432/block_e
Connection successful
PostgreSQL version: PostgreSQL 16.15 on x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit
Connection closed cleanly
```

(Worker stdout rendered checkmarks as `???` because of container locale; connection succeeded, exit 0.)

**Result:** **PASS** (collection no longer SystemExits; script still performs the check)

---

### E-fix-2 — E3 re-embed trigger, DB auth

**Files changed:** `services/block-e-chunking/tests/verify_component6_re_embed_trigger.py`  
**`.bak`:** `services/block-e-chunking/tests/verify_component6_re_embed_trigger.py.bak`

**Root cause:** credential/DB-name mismatch, not re-embed logic. The E3 script used `postgresql+asyncpg://postgres:verify@localhost:5433/block_e_verify`. This block’s `docker-compose.yml` defines `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`, `POSTGRES_DB=block_e`, host port `5433`. Compose names were not changed.

**Change:** URL set to `postgresql+asyncpg://postgres:postgres@localhost:5433/block_e`. Trigger logic not modified.

**Re-run** (wrapper that previously failed):

```
$env:PYTHONPATH = "D:\PROJECTS\A sync Ai final\services\block-e-chunking"
python -m pytest tests/test_block_e.py -v --tb=short -s
```

```
tests/test_block_e.py::test_E1_chunk_integrity PASSED
tests/test_block_e.py::test_E2_structural_throughput PASSED
tests/test_block_e.py::test_E3_reembed_triggered PASSED
tests/test_block_e.py::test_E4_identical_chunk_ids_on_3_reprocess PASSED

============================= 4 passed in 34.72s ==============================
```

After auth was fixed, that first `test_E3_reembed_triggered` run returned 0 (PASS). Distinction: this was a connection-string mismatch; the trigger path ran once auth matched compose.

A later extra direct invocation of `verify_component6_re_embed_trigger.py` then failed Test 5 (`Expected 10 jobs with model version v2, got 20`) because that query is **not tenant-scoped** and leftover `v2` rows remained from the passing run. That is isolation in the verify script, not the original auth bug. See §6.3. The listed E3 pytest case already passed.

**Result:** **PASS** (listed E3 test)

---

### E-fix-3 — E4 idempotency (`chunk_id` stability)

**Files changed:** `services/block-e-chunking/tests/verify_e4_idempotency.py`  
**`.bak`:** `services/block-e-chunking/tests/verify_e4_idempotency.py.bak`

**Root cause (differs from the uuid4 guess):** `chunk_id` generation was already deterministic. `ChunkIDGenerator` is `SHA256(tenant_id | document_id | document_version | chunker_version | chunk_type | chunk_index | content_hash)`. The prior session printed **identical** IDs across 3 runs, then crashed on `print("   ✓ ...")` (`UnicodeEncodeError` / cp1252) before `assert ... is True`.

**Change:** replaced `✓`/`✗` prints with ASCII `OK`/`FAIL`. Chunk-ID generator not rewritten.

**Re-run:** `tests/test_block_e.py::test_E4_identical_chunk_ids_on_3_reprocess` (same suite as above):

```
================================================================================
E4 IDEMPOTENCY VERIFICATION (v7.0 §4.5)
================================================================================

[1] Running first processing...
   Generated 3 chunks
   Chunk IDs: ['1156d5ce9dcf4b53b8ea9c9d23af0cb472454a15adbd3a6aeed2631587a1012c', '8f88047929b39d1d2c0c1b4ff4a206930f5537451e1322050c04216191fe95ef', 'b20933984bef628464a6e9ae958a525b6774b38c13b49b1ccfc55272d24fee95']

[2] Running second processing...
   Generated 3 chunks
   Chunk IDs: ['1156d5ce9dcf4b53b8ea9c9d23af0cb472454a15adbd3a6aeed2631587a1012c', '8f88047929b39d1d2c0c1b4ff4a206930f5537451e1322050c04216191fe95ef', 'b20933984bef628464a6e9ae958a525b6774b38c13b49b1ccfc55272d24fee95']

[3] Running third processing...
   Generated 3 chunks
   Chunk IDs: ['1156d5ce9dcf4b53b8ea9c9d23af0cb472454a15adbd3a6aeed2631587a1012c', '8f88047929b39d1d2c0c1b4ff4a206930f5537451e1322050c04216191fe95ef', 'b20933984bef628464a6e9ae958a525b6774b38c13b49b1ccfc55272d24fee95']

[4] Verifying chunk_id consistency across runs...
   OK All three runs produced identical chunk_ids
   OK All three runs produced 3 chunks (consistent)

[5] Verifying chunk content consistency across runs...
   OK All chunk content is identical across runs

[6] Verifying chunk_id changes when content changes...
   OK Chunk_ids changed when content changed (correct behavior)

[7] Verifying chunk_id changes when chunker_version changes...
   OK Chunk_ids changed when chunker_version changed (correct behavior)

================================================================================
E4 IDEMPOTENCY VERIFICATION: PASSED
================================================================================
PASSED
```

Three runs, 0 drift. **Result:** **PASS**

---

### E-fix-4 — E2 throughput (diagnose first)

**Files changed:** `services/block-e-chunking/tests/verify_component8_throughput_harness.py` (ASCII prints only)  
**`.bak`:** `services/block-e-chunking/tests/verify_component8_throughput_harness.py.bak`

**Diagnosis (harness re-run once with `$env:PYTHONIOENCODING = "utf-8"`, no chunking/embed code change):**

| Measurement | Value | vs ≥500 docs/min/worker |
|-------------|-------|-------------------------|
| Prose end-to-end (10 docs) | 598.2 docs/min | above |
| Code end-to-end (10 docs) | 444.7 docs/min | below (snapshot, not the sustained number) |
| Sustained 30s, mock provider, overall | **554.2 docs/min** | above |
| Sustained min/avg/max batch | 475.7 / 558.5 / 690.4 | min batch dipped under 500; overall above |

Harness uses `MockEmbeddingProvider`, ~38-word prose fixtures, 30s not 10 minutes. Prior pytest failure was `UnicodeEncodeError` on `✓`, not a measured shortfall. Chunking/embedding path was **not** changed to chase the floor.

**Change made:** same class of encoding fix as E4 — ASCII `OK`/`FAIL` so `test_E2_structural_throughput` can finish under Windows cp1252 without `PYTHONIOENCODING`. Not a throughput optimization.

**Re-run of the listed test:** `tests/test_block_e.py::test_E2_structural_throughput PASSED` (see E-fix-2 suite, 4 passed / 34.72s).

**Result:** **PASS** for the listed wrapper. Full 10-minute E2 signoff harness (`verify_e2_10min_sustained.py`) was not run this session.

---

### G-fix-1 — `qdrant-client` / `query_points`

**Files changed:** `services/block-g-vector-search/requirements.txt`  
**`.bak`:** `services/block-g-vector-search/requirements.txt.bak`

**Root cause:** pin was already `qdrant-client>=1.12.1`; the installed interpreter had **1.9.1**, which has no `query_points` (`query_points` landed around client 1.10+ / 1.12). `app/services/qdrant_store.py` calls `self._client.query_points(...)`.

**Choice:** **bump the pin**, not rewrite to legacy `search()`. Nothing else in Block G’s `requirements.txt` constrained the client. Server image is `qdrant/qdrant:v1.12.1`. Pin set to `qdrant-client==1.12.1` to match that server. Between 1.9.1 and 1.12.1, `query_points` is additive; `search()` deprecation/removal is later (1.15+). No rewrite of filter kwargs required — G1–G4 passed against real Qdrant with the existing `query=` / `query_filter=` / `limit=` / `with_payload=` call.

**Install:** `python -m pip install "qdrant-client==1.12.1"` succeeded on Python 3.14. `hasattr(QdrantClient, 'query_points')` → `True`; package version `1.12.1`.

**Re-run** against `block-g-test-qdrant` (`localhost:6335`), not a mock:

```
$env:VECTOR_DB_TYPE = "qdrant"
$env:QDRANT_HOST = "localhost"
$env:QDRANT_PORT = "6335"
$env:PYTHONPATH = "D:\PROJECTS\A sync Ai final\services\block-g-vector-search"
python -m pytest tests/ -v --tb=short -s
```

```
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\PROJECTS\A sync Ai final\services\block-g-vector-search
configfile: pytest.ini
collecting ... collected 8 items

tests/test_acl_prefilter.py::test_G2_acl_prefilter_zero_leak PASSED
G2 ACL prefilter: 0 restricted chunks across 15 cases — PASS

tests/test_block_g.py::test_G1_recall_at_10_ge_085 PASSED
G1 Recall@10 average: 1.0000 (threshold 0.85)

tests/test_block_g.py::test_G2_acl_zero_leaks PASSED
G2 ACL prefilter: 0 restricted chunks across 15 cases — PASS

tests/test_block_g.py::test_G3_p95_le_150ms PASSED
G3 latency: n=100 avg=17.57ms p95=33.79ms (threshold 150ms)

tests/test_block_g.py::test_G4_model_version_handling PASSED
G4 model-version handling: PASS (tagged, filtered, no cross-model ranking claim)

tests/test_latency.py::test_G3_latency_p95 PASSED
G3 latency: n=100 avg=19.16ms p95=42.14ms (threshold 150ms)

tests/test_model_versions.py::test_G4_model_version_filter PASSED
G4 model-version handling: PASS (tagged, filtered, no cross-model ranking claim)

tests/test_recall.py::test_G1_recall_at_10 PASSED
G1 Recall@10 average: 1.0000 (threshold 0.85)

============================= 8 passed in 35.91s ==============================
```

**Result:** **PASS** (G1–G4, Phase 2 real Qdrant)

---

## 6.2 D4 status

**Branch taken: local-fixable.**

D4’s failing test (`tests/test_D4_key_rotation_local.py`) uses `postgresql://postgres:verify@localhost:5435/block_d_verify` — Block D’s own `docker-compose.yml` Postgres (`block-d-verify-pg`), not hosted Supabase. `CREATE EXTENSION IF NOT EXISTS pgcrypto` was added to:

1. `migrations/001_create_tenants_table.sql`
2. `initdb/01_pgcrypto.sql` (applied on **fresh** init only)
3. the D4 fixture (needed because the existing volume was already initialized; volumes were not deleted)

Cloud `*_real.py` / `SUPABASE_DB_URL` paths were not used and pgcrypto was not enabled on hosted Supabase.

If you still need it on hosted Supabase yourself, the SQL is:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

---

## 6.3 Noticed but not fixed

- `services/block-d-storage/verify_component1_key_creation.py` constructs `EncryptionClient(db_client)` without `vault_client` (second instance of D-fix-1’s stale call site).
- Other Block E scripts still point at `postgres:verify` / `block_e_verify` (`verify_component1_consumer.py`, `verify_component5_tenant_isolation.py`, `verify_component7_orphan_handler.py`, `verify_document_id_join_check_real_postgres.py`, `alembic.ini`). Only E3’s `verify_component6` was in scope.
- `verify_component6_re_embed_trigger.py` Test 5 selects `EmbeddingJob` rows with `model_version_target == "v2"` and **no tenant filter**, so a second run in the same DB fails after a clean first pass.
- `tests/test_asyncresult_from_host.py` is still a `test_*.py` script with module-level Redis/Celery side effects (not collected as a test function; can still execute on import).
- `docker-compose.yml` for Block D still comments `docker compose ... config --services` (forbidden in this environment; comment only).
- Dirty evidence files from earlier sessions, not edited here: `services/block-f-lexical-search/evidence/lag_measurement.csv`, `services/block-i-signals/evidence/i1_privacy_report.json`, `i1_privacy_report_phase2.json`, `i3_freshness_report.json`, `i3_freshness_report_phase2.json`.
- `backend/requirements.txt` still has `qdrant-client==1.12.0` (out of Block G scope).
- E2 `test_E2_structural_throughput` is a 30s mock-provider harness, not the 10-minute ≥500 docs/min signoff run.
- `tests/test_block_d.py` nested pytest `WinError 50` DuplicateHandle (prior session); not re-opened.
- Host DNS still resolves compose hostname `postgres` to public IPs (`207.207.210.107` / `.229`); the worker container is the intended place to run the connectivity script.

---

## 6.4 Fixes that did not work

None. No item hit the 3-attempt stop. All listed re-verify tests passed on the first post-fix run.

---

## Summary

| ID | Listed failure | Result after fix |
|----|----------------|------------------|
| D-fix-1 | `EncryptionClient` TypeError | **PASS** (4 tests) |
| D-fix-2 | D2 `InvalidAccessKeyId` | **PASS** |
| D-fix-3 | D4 `pgcrypto` | **PASS** (local compose PG) |
| E-fix-1 | collection `SystemExit` | **PASS** |
| E-fix-2 | E3 DB auth | **PASS** |
| E-fix-3 | E4 chunk_id / UnicodeEncodeError | **PASS** (IDs already stable) |
| E-fix-4 | E2 throughput | **PASS** (encoding; 554.2 docs/min mock 30s; no pipeline change) |
| G-fix-1 | `query_points` on 1.9.1 | **PASS** (8 tests, Qdrant `:6335`, client 1.12.1) |

Stopped here. No commit, no push, `SIGNOFF.md` unchanged.
