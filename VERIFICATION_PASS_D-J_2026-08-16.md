# Independent Verification Pass — Blocks D–J

**Date:** 2026-08-16  
**Type:** Read-and-report only. This file is not `SIGNOFF.md`. No criteria were marked in any `SIGNOFF.md`.

---

## Repo / branch discrepancy (read this first)

The original prompt specified:

- repo: `logicinnovationlabs/Synq-AI`
- branch: `Ishu`

The actual working folder `D:\PROJECTS\A sync Ai final` is:

```
On branch Pratham
Your branch is up to date with 'origin/Pratham'.
5ce77b1 Add: Block N completed and tested
origin	https://github.com/logicinnovationlabs/Sync-AI-Final.git (fetch)
origin	https://github.com/logicinnovationlabs/Sync-AI-Final.git (push)
```

Branch switching was not authorized. **Every row below was tested against `Sync-AI-Final` / `Pratham` / `5ce77b1`, not `Synq-AI` / `Ishu`.**

Python actually used:

```
C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\python.exe
3.14.0 (tags/v3.14.0:ebf955d, Oct  7 2025, 10:15:03) [MSC v.1944 64 bit (AMD64)]
```

Architecture doc `Glean Arch made by Glean v1.3.1` is not in this tree. Criterion IDs below are taken from each block's `SIGNOFF.md` (which cites Glean Arch v1.3 §24) and the original prompt's examples (D1–D4, E1–E4).

---

## Ground truth after Docker reinstall (before any bring-up)

```
Docker version 29.6.2, build dfc4efb

CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

Zero containers. Qdrant on `:6333` was **not** reachable (`Unable to connect to the remote server`) despite the resume note that Qdrant was confirmed up. MinIO `:9000` and Postgres `:5435` were also down. Each remaining block's own compose was started independently.

After this session's per-block bring-up:

```
NAMES                              STATUS                    PORTS
block-i-postgres-test              Up (healthy)              0.0.0.0:15433->5432/tcp
block-h-test-neo4j                 Up (healthy)              0.0.0.0:7475->7474/tcp, 0.0.0.0:7688->7687/tcp
block-g-test-redis                 Up (healthy)              0.0.0.0:6381->6379/tcp
block-g-test-qdrant                Up (healthy)              0.0.0.0:6335->6333/tcp
block-e-chunking-celery-worker-1   Up
block_e_postgres                   Up (healthy)              0.0.0.0:5433->5432/tcp
block-e-chunking-redis-1           Up (healthy)              0.0.0.0:6379->6379/tcp
block-d-verify-pg                  Up (healthy)              0.0.0.0:5435->5432/tcp
block-d-verify-minio               Up                        0.0.0.0:9000-9001->9000-9001/tcp
```

No HashiCorp Vault container was started: Block D's own `docker-compose.yml` declares Postgres + MinIO only. D4 uses an in-process table vault against that Postgres.

`git status` also showed `services/block-f-lexical-search/evidence/lag_measurement.csv` modified (artifact of the prior-session F Phase 1 run). Not reverted; not committed.

---

## Block D — Storage Substrate

**Commit:** `5ce77b1`  
**Service folder:** `services/block-d-storage`  
**Phase reached:** Phase 2 attempted against this session's `block-d-verify-pg` (`localhost:5435`) and `block-d-verify-minio` (`localhost:9000`). HashiCorp/KMS vault is not in this block's compose; table-backend vault is used by D4 tests. Cloud Supabase tests ERROR because `services/block-d-storage/.env` does not exist (`Test-Path` = `False`) and `SUPABASE_DB_URL` is unset.  
**pgcrypto:** `SELECT extname FROM pg_extension WHERE extname='pgcrypto'` returned **0 rows**. Extension was **not** enabled (operator-owned infra; not enabled by this pass).

### Flagged finding 1 — `BackupMetadata` forward reference

Source still has the annotation **before** the class:

```
_backup_metadata_store: Dict[str, BackupMetadata] = {}
...
@dataclass
class BackupMetadata:
```

Import on this machine:

```
IMPORT_OK <class 'backup_cli.backup_restore.BackupMetadata'>
```

**Prior sandbox finding REFUTED here.** Python 3.14 deferred/lazy annotation evaluation means the forward reference does not raise `NameError` at import. Collection of backup tests succeeded. This can still break on 3.11/3.12 without `from __future__ import annotations`; it did not break on the installed 3.14.

### Flagged finding 2 — `EncryptionClient.__init__` / `vault_client`

```
signature (self, db_client, vault_client)
NOARG TypeError EncryptionClient.__init__() missing 2 required positional arguments: 'db_client' and 'vault_client'
ONEARG TypeError EncryptionClient.__init__() missing 1 required positional argument: 'vault_client'
```

The live suite constructs it with one argument in `tests/test_encryption.py`:

```
EncryptionClient(mock_db)
```

**Prior finding CONFIRMED** against this checkout. Actual pytest failures:

```
tests\test_encryption.py:26: in test_pgsodium_verification_fails_without_extension
    EncryptionClient(mock_db)
E   TypeError: EncryptionClient.__init__() missing 1 required positional argument: 'vault_client'
tests\test_encryption.py:31: in test_encrypt_requires_pgsodium
    EncryptionClient(mock_db)
E   TypeError: EncryptionClient.__init__() missing 1 required positional argument: 'vault_client'
tests\test_encryption.py:36: in test_decrypt_requires_pgsodium
    EncryptionClient(mock_db)
E   TypeError: EncryptionClient.__init__() missing 1 required positional argument: 'vault_client'
tests\test_encryption.py:41: in test_rotate_key_requires_pgsodium
    EncryptionClient(mock_db)
E   TypeError: EncryptionClient.__init__() missing 1 required positional argument: 'vault_client'
```

(The tests still expect `RuntimeError` matching `pgsodium extension is not enabled`; the constructor never gets that far.)

### Full suite (this session)

```
================== 11 failed, 55 passed, 3 errors in 31.24s ===================
```

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| D1 | Provision 10 tenants in <5 min | **PASS** | `test_D1_provisioning_time_local` PASSED against `localhost:5435` this session. Mock `test_D1_provisioning_time` also PASSED. |
| D2 | Backup/restore row+object checksums match | **FAIL** | Local MinIO path: `InvalidAccessKeyId` (test uses `verify`/`verifyverify`; compose MinIO is `minioadmin`/`minioadmin`). |
| D3 | 20/20 cross-tenant reads blocked at storage layer | **PASS** | `test_D3_schema_permission_isolation` PASSED; extra `test_D3_storage_isolation_real_postgres` also PASSED this session. |
| D4 | Key rotation under load, 0 downtime / 0 data loss | **BLOCKED** | `pgcrypto` not enabled on `block_d_verify`. Test failed before load ran. Not enabled by this pass. |

### Failure / error output (pasted)

**D2 local (MinIO):**

```
E   botocore.exceptions.ClientError: An error occurred (InvalidAccessKeyId) when calling the ListBuckets operation: The Access Key Id you provided does not exist in our records.
```

Test constants: `MINIO_ENDPOINT=http://localhost:9000`, `MINIO_ACCESS_KEY=verify`, `MINIO_SECRET_KEY=verifyverify`. Compose: `MINIO_ROOT_USER=minioadmin`, `MINIO_ROOT_PASSWORD=minioadmin`. MinIO live check this session: HTTP 200.

**D4 local (pgcrypto):**

```
E   RuntimeError: pgcrypto extension is not enabled in the database. Please enable pgcrypto on the database instance before using this component.
```

**D1/D2/D4 cloud (`*_real.py`):**

```
E   RuntimeError: SUPABASE_DB_URL not found in environment variables
E   RuntimeError: Database connection string not found in environment variables. Please set SUPABASE_DB_URL, DATABASE_URL, or POSTGRES_URL in .env file
```

Expected: `SUPABASE_DB_URL` pointing at the cloud/control-plane Postgres used for those tests. `services/block-d-storage/.env` is absent. `backend/.env` was not opened.

**`test_backup_restore.py::test_backup_checksum_consistency`:**

```
E   AssertionError: assert '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a' != '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'
```

Two backups of empty mock schemas produced the same SHA-256 (empty JSON `[]`).

**`tests/test_block_d.py` wrappers (nested `subprocess.run` of pytest):**

```
E   OSError: [WinError 50] The request is not supported
```

(`_winapi.DuplicateHandle` during nested pytest). Direct criterion files for D1/D3 still ran and PASSED; D2/D4 direct files FAILED as above.

### SIGNOFF.md discrepancy

`services/block-d-storage/SIGNOFF.md` marks D1–D4 **PASS** (Phase 2, 2026-08-04, pgcrypto v1.3, MinIO round-trip). This session: D1 PASS, D3 PASS, D2 FAIL, D4 BLOCKED, plus EncryptionClient suite FAIL. Do not treat SIGNOFF as current.

---

## Block E — Chunking / Embedding

**Commit:** `5ce77b1`  
**Service folder:** `services/block-e-chunking`  
**Phase reached:** Mixed. Redis `:6379`, Postgres `:5433` (`block_e` / password `postgres`), and celery-worker were up from this block's compose. E1/E4 are unit-level (no DB). E2 script crashed on console encoding before measuring throughput. E3 could not authenticate: verify script uses `postgresql+asyncpg://postgres:verify@localhost:5433/block_e_verify`; compose DB is `block_e` with password `postgres`. Database `block_e_verify` was not created (infra/config mismatch; not changed by this pass).

### Flagged finding — tree-sitter `Language(...)` arity

`code_chunker.py`:

```
self.language_parsers['python'] = tree_sitter.Language(python_language())
```

Pinned in `services/block-e-chunking/requirements.txt`: `tree-sitter==0.21.3` (0.21.3 `Language.__init__(self, path_or_ptr, name)` is **two** arguments).

Installed:

```
Name: tree-sitter
Version: 0.26.0
ONE_ARG_OK <class 'tree_sitter.Language'>
```

**E1 did not fail because of this on the installed 0.26.0.** The pin-vs-call mismatch is real in the file/requirements; it is **not** what broke E1 in this environment. If 0.21.3 were installed, the one-arg call would be expected to TypeError.

### Flagged finding — `tests/test_container_db_connection.py` collection hygiene

Bare script: `psycopg2.connect("postgresql://postgres:postgres@postgres:5432/block_e")` then `sys.exit(1)` on failure. Hostname `postgres` resolved to `207.207.210.107` / `207.207.210.229` from the host (not the compose network).

`python -m pytest tests/ --collect-only -q` this session:

```
Testing connection to: postgresql://postgres:postgres@postgres:5432/block_e
✗ Connection failed: connection to server at "postgres" (207.207.210.107), port 5432 failed: Connection timed out
...
INTERNALERROR>   File "...\tests\test_container_db_connection.py", line 29, in <module>
INTERNALERROR>     sys.exit(1)
INTERNALERROR> SystemExit: 1
4 tests collected, 1 error in 50.57s
exit_code: 3
```

**CONFIRMED:** collecting `tests/` as one invocation errors on this file. Distinct from E1–E4.

A second hygiene file, `tests/test_asyncresult_from_host.py`, also runs at import. After ignoring only the DB script:

```
ERROR collecting tests/test_asyncresult_from_host.py
UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'
Interrupted: 1 error during collection
EXIT=2
```

E1–E4 were re-run with both files ignored so criterion results were not obscured.

### E1–E4 (excluding hygiene scripts)

```
FAILED tests/test_block_e.py::test_E2_structural_throughput
FAILED tests/test_block_e.py::test_E3_reembed_triggered
FAILED tests/test_block_e.py::test_E4_identical_chunk_ids_on_3_reprocess
========================= 3 failed, 1 passed in 1.81s =========================
```

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| E1 | Chunk integrity (AST, 0 mid-function/class splits) | **PASS** | `test_E1_chunk_integrity` PASSED (`verify_component4_code_chunker.py`). tree-sitter 0.26.0 accepted the one-arg `Language()` call. |
| E2 | Throughput ≥500 docs/min sustained | **FAIL** | Wrapper runs `verify_component8_throughput_harness.py`; process exits 1 on `UnicodeEncodeError` printing `✓`. |
| E3 | Re-embed trigger | **FAIL** | `password authentication failed for user "postgres"` against `postgres:verify@localhost:5433/block_e_verify`. |
| E4 | Identical chunk_ids across 3 reprocess runs | **FAIL** | Three runs printed identical IDs, then the test raised `UnicodeEncodeError` on `✓ All three runs produced identical chunk_ids` before `assert ... is True`. Suite result is FAIL. |

### Failure output (pasted)

**E2:**

```
File "...\verify_component8_throughput_harness.py", line 50, in verify_throughput_harness
    print(f"   \u2713 Document generation works")
UnicodeEncodeError: 'charmap' codec can't encode character '\u2713' in position 3: character maps to <undefined>
```

**E3:**

```
[FAIL] Verification failed with exception: password authentication failed for user "postgres"
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "postgres"
```

Verify script URL: `postgresql+asyncpg://postgres:verify@localhost:5433/block_e_verify`. Compose: `POSTGRES_PASSWORD=postgres`, `POSTGRES_DB=block_e`.

**E4 (IDs were identical, then crash):**

```
[1] Running first processing...
   Generated 3 chunks
   Chunk IDs: ['1156d5ce9dcf4b53b8ea9c9d23af0cb472454a15adbd3a6aeed2631587a1012c', ...]
[2] Running second processing...
   Chunk IDs: ['1156d5ce9dcf4b53b8ea9c9d23af0cb472454a15adbd3a6aeed2631587a1012c', ...]
[3] Running third processing...
   Chunk IDs: ['1156d5ce9dcf4b53b8ea9c9d23af0cb472454a15adbd3a6aeed2631587a1012c', ...]
[4] Verifying chunk_id consistency across runs...
...
tests\verify_e4_idempotency.py:87: in test_e4_idempotency
    print("   \u2713 All three runs produced identical chunk_ids")
UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'
```

### SIGNOFF.md discrepancy

`services/block-e-chunking/SIGNOFF.md` marks E1–E7 / Block E **PASS** (closeout 2026-08-04/05). This session: E1 PASS, E2 FAIL, E3 FAIL, E4 FAIL. E1/E as “Done” in SIGNOFF is **not** what the live suite produced.

---

## Block F — Lexical Search

**Commit:** `5ce77b1`  
**Service folder:** `services/block-f-lexical-search`  
**Phase reached:** **Phase 1 mock only** (carried forward from the pre-reinstall session; mock tests do not depend on Docker state). Phase 2 OpenSearch was not re-run this session (not in the resume remaining list; `snyq_opensearch_dev` was gone after reinstall).

Carried Phase 1 command: `$env:SEARCH_BACKEND = "mock"; python -m pytest tests/ -v --tb=short -s`

```
============================= 11 passed in 2.65s ==============================
F1 latency: n=100 avg=6.89ms p95=10.79ms (threshold 200ms)
F2 ACL enforcement: 0 unauthorized across 15 cases
F3 index lag: n=20 avg=0.0078s p95=0.0143s (threshold 30s)
F4 facet accuracy: 100% match
```

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| F1 | Query latency p95 ≤ 200ms | **PASS** (Phase 1 mock) | p95=10.79ms (also 13.25ms in `test_latency.py` duplicate). |
| F2 | ACL 0 unauthorized / 15 cases | **PASS** (Phase 1 mock) | `leaked=[]` all 15. |
| F3 | Index lag p95 < 30s | **PASS** (Phase 1 mock) | p95=0.0143s. |
| F4 | Facet accuracy 100% | **PASS** (Phase 1 mock) | mismatches: none. |

### SIGNOFF.md discrepancy

SIGNOFF Phase 1 = PASS; Phase 2 = PENDING. This pass matches Phase 1 PASS and did not produce Phase 2 evidence. No contradiction on Phase 2 (still unverified here).

---

## Block G — Vector Search (Qdrant)

**Commit:** `5ce77b1`  
**Service folder:** `services/block-g-vector-search`  
**Vector DB actually used:** Qdrant (`VECTOR_DB_TYPE`, `app/services/qdrant_store.py`). Not pgvector/Weaviate.

### Phase 1 (carried forward, mock)

```
VECTOR_DB_TYPE=mock
============================== 8 passed in 3.02s ==============================
G1 Recall@10 average: 1.0000 (threshold 0.85)
G2 ACL prefilter: 0 restricted chunks across 15 cases
G3 latency: n=100 avg=1.35ms p95=2.00ms (threshold 150ms)
G4 model-version handling: PASS
```

### Phase 2 (this session, real Qdrant)

Started this block's `docker-compose.test.yml`: `block-g-test-qdrant` `qdrant/qdrant:v1.12.1` on `localhost:6335` (healthy; `/readyz` → `200 all shards are ready`).

```
VECTOR_DB_TYPE=qdrant; QDRANT_HOST=localhost; QDRANT_PORT=6335
============================= 8 failed in 29.08s ==============================
```

Installed client vs pin:

```
requirements.txt: qdrant-client>=1.12.1
pip show qdrant-client → Version: 1.9.1
```

| ID | Criterion | Phase 1 | Phase 2 | Evidence |
|----|-----------|---------|---------|----------|
| G1 | Recall@10 ≥ 0.85 | **PASS** | **FAIL** | Phase 2: `AttributeError: 'QdrantClient' object has no attribute 'query_points'` |
| G2 | ACL prefilter 0 leaks | **PASS** | **FAIL** | Same `query_points` error. |
| G3 | Latency p95 ≤ 150ms | **PASS** | **FAIL** | Same `query_points` error. |
| G4 | Model-version handling | **PASS** | **FAIL** | Same `query_points` error. |

### Failure output (pasted, representative; all 8 tests same)

```
app\services\qdrant_store.py:216: in search
    response = self._client.query_points(**kwargs)
E   AttributeError: 'QdrantClient' object has no attribute 'query_points'
```

Repeated for: `test_G2_acl_prefilter_zero_leak`, `test_G1_recall_at_10_ge_085`, `test_G2_acl_zero_leaks`, `test_G3_p95_le_150ms`, `test_G4_model_version_handling`, `test_G3_latency_p95`, `test_G4_model_version_filter`, `test_G1_recall_at_10`.

### SIGNOFF.md discrepancy

SIGNOFF marks G1–G4 **PASS** in both Phase 1 and Phase 2 (2026-08-05, Qdrant `:6333`). This session: Phase 1 PASS (carried), Phase 2 **all FAIL** against a healthy Qdrant 1.12.1 with installed `qdrant-client==1.9.1`.

---

## Block H — Knowledge Graph (Neo4j)

**Commit:** `5ce77b1`  
**Service folder:** `services/block-h-graph`  
**Phase reached:** Phase 1 mock **and** Phase 2 Neo4j CE 5.26 (`block-h-test-neo4j`, bolt `localhost:7688`).

Phase 1 (`GRAPH_BACKEND=mock`):

```
============================== 6 passed in 0.22s ==============================
H1 Edge fidelity: PASS (100% match)  total expected: 183 actual: 183
H2 Traversal latency: PASS  runs=50 avg=0.059 ms p95=0.107 ms (threshold 100 ms)
H3 Merge/split integrity: PASS  redirected=4 orphans_after_merge=0 restored_edges=4
```

Phase 2 (`GRAPH_BACKEND=neo4j`, `NEO4J_URI=bolt://localhost:7688`, `NEO4J_PASSWORD=blockh-dev-password`):

```
============================= 6 passed in 21.36s ==============================
H1 Edge fidelity: PASS (100% match)  183/183
H2 Traversal latency: PASS  runs=50 avg=12.877 ms p95=12.409 ms (threshold 100 ms)
H3 Merge/split integrity: PASS  redirected=4 orphans=0 restored_edges=4
```

| ID | Criterion | Phase 1 | Phase 2 | Evidence |
|----|-----------|---------|---------|----------|
| H1 | Edge fidelity 100% | **PASS** | **PASS** | 183/183 both phases. |
| H2 | Traversal p95 ≤ 100ms | **PASS** | **PASS** | mock p95=0.107ms; Neo4j p95=12.409ms. |
| H3 | Merge/split 0 orphans | **PASS** | **PASS** | redirected=4, orphans=0, restored=4 both phases. |

### SIGNOFF.md discrepancy

SIGNOFF already marks H1–H3 PASS Phase 1 and Phase 2. This session agrees. Reviewer still PENDING in SIGNOFF; this pass does not sign that row.

---

## Block I — Activity Signals

**Commit:** `5ce77b1`  
**Service folder:** `services/block-i-signals`  
**Phase reached:** Phase 1 mock **and** Phase 2 Postgres (`block-i-postgres-test` `localhost:15433`, `postgresql://signals:signals@localhost:15433/block_i_signals`).

Phase 1 (`SIGNALS_BACKEND=mock`):

```
============================== 8 passed in 0.65s ==============================
I1 PASS  4 privacy cases
I2 PASS  purged=8
I3 PASS  p95=0.0020s (threshold 900s)
```

Phase 2 (`SIGNALS_BACKEND=postgres`):

```
============================= 8 passed in 12.82s ==============================
I1 PASS  4 privacy cases; report=...\evidence\i1_privacy_report_phase2.json
I2 PASS  purged=8; report=...\evidence\i2_retention_report_phase2.json
I3 PASS  p95=0.1895s (threshold 900s); report=...\evidence\i3_freshness_report_phase2.json
```

Also PASSED both phases: idempotent reingest, tenant isolation, missing-scope 403, health.

| ID | Criterion | Phase 1 | Phase 2 | Evidence |
|----|-----------|---------|---------|----------|
| I1 | Privacy threshold | **PASS** | **PASS** | 4/4 cases. |
| I2 | Retention enforcement | **PASS** | **PASS** | purged=8. |
| I3 | Signal freshness p95 ≤ 15m (900s) | **PASS** | **PASS** | mock p95=0.0020s; postgres p95=0.1895s. |

### SIGNOFF.md discrepancy

SIGNOFF marks I1–I3 PASS Phase 1 and Phase 2. This session agrees. Reviewer still PENDING in SIGNOFF.

---

## Block J — Query Federator

**Commit:** `5ce77b1`  
**Service folder:** `services/block-j-query-federator`  
**Phase reached:** **Phase 1 only.** `tests/conftest.py` defaults `ACL_BACKEND=memory`, `RERANKER_BACKEND=mock`, `EMBEDDING_BACKEND=mock`. J Phase 2 requires real F, G, and H services. This session: F Phase 2 not run; G Phase 2 FAILED; H Phase 2 PASSED. Phase 2 for J was **not attempted**.

```
============================= 19 passed in 5.71s ==============================
J1 p95 latency: 11.35 ms (threshold 800 ms)
J2 ACL enforcement: 0 unauthorized across 15 cases x backend combos
J3 NDCG@10 average: 1.0000 (threshold 0.80)
J4 graceful degradation: 0 5xx with G killed and with H killed
```

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| J1 | 100 queries p95 ≤ 800ms | **PASS** (Phase 1) | p95=11.35 ms (duplicate 14.60 ms). |
| J2 | 15 red-team × backends → 0 unauthorized | **PASS** (Phase 1) | 0 unauthorized. |
| J3 | 30-query NDCG@10 ≥ 0.80 | **PASS** (Phase 1) | average 1.0000. |
| J4 | Kill G / Kill H → partial OK, 0 5xx | **PASS** (Phase 1) | 0 5xx in mock kill paths. |

### SIGNOFF.md discrepancy

SIGNOFF marks J1–J4 PASS from a local 15-passed run. This session’s Phase 1 19-passed run agrees on J1–J4. It is **not** Phase 2 against live F/G/H.

---

## Flagged-item recap vs original sandbox hunches

| Item | This environment |
|------|------------------|
| D `BackupMetadata` annotation before class breaks import | **Did not reproduce** on Python 3.14 (import OK). |
| D `EncryptionClient` requires `vault_client`; tests call `EncryptionClient(mock_db)` | **Confirmed.** Four tests FAIL with `TypeError`. |
| E `Language(python_language())` one-arg vs pin 0.21.3 two-arg | Pin/API mismatch is real. **Installed 0.26.0 accepts one arg. E1 PASSED.** E1 did not fail for this reason here. |
| E `test_container_db_connection.py` crashes `pytest tests/` collection | **Confirmed.** `SystemExit: 1` after connect timeout to host `postgres` (207.207.210.107). |

---

## Infra items left for the operator (not changed this pass)

- Enable `pgcrypto` on `block-d-verify-pg` / `block_d_verify` if D4 is to be re-run (or confirm it should stay off).
- Align MinIO keys used by `test_D2_backup_restore_local.py` (`verify`/`verifyverify`) with compose (`minioadmin`/`minioadmin`), or the reverse — not done here.
- Set `SUPABASE_DB_URL` if cloud D1/D2/D4 `*_real.py` tests are in scope. `services/block-d-storage/.env` is missing.
- E3 verify script expects `postgres:verify` / database `block_e_verify` on `:5433`; this block’s compose provides `postgres:postgres` / `block_e`.
- G Phase 2: installed `qdrant-client==1.9.1` lacks `query_points` used by `qdrant_store.py`; pin is `>=1.12.1`. No package upgrade performed.
- F Phase 2 OpenSearch and J Phase 2 against live F/G/H were not run.

Stop. No fixes. No `SIGNOFF.md` edits. No Blocks K–O.
