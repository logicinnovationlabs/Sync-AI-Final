# Verification Pass — Block K Phase 2 (real Postgres + MinIO)

**Date:** 2026-08-17  
**Type:** Diagnose whether K’s signoff suite (and L2’s citation GETs) were Phase 1 in-memory doubles; if so, wire to Block D verify Postgres/MinIO and re-run K1–K3 + L2.  
**This file is not `SIGNOFF.md`.**

**Commit tested (HEAD, uncommitted work on top):** `5ce77b1a97f3bf0ea0ba980282940f517e7ad911` (`Add: Block N completed and tested`)  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

`.env` / `backend/.env` were never opened. Compose-declared names only for Block D verify services.

No commits, no pushes, no `SIGNOFF.md` edits.

---

## 5.1 Part A — Diagnosis (before any code change)

**Both K’s signoff suite and L2’s 93 citation GETs were Phase 1.** They were the same in-memory fixture, not a separate live K process.

### K signoff (`k_app`)

`backend/tests/test_block_k_signoff.py` takes `k_app`. Construction before this session:

```183:187:backend/tests/conftest.py
    from app.services.document_reader.store import InMemoryDocumentStore
    from app.services.document_reader.acl_checker import MockACLChecker

    store = InMemoryDocumentStore(settings)
    acl = MockACLChecker()
```

`InMemoryDocumentStore` is a dict double (`self._docs: Dict[tuple[str, str], ...]`, `self._objects: Dict[str, bytes]`). `connect()` is a no-op. No Postgres, no MinIO, no network.

A factory switch already existed and was **bypassed**:

```221:225:backend/app/services/document_reader/store.py
def create_document_store(settings: Settings) -> InMemoryDocumentStore | MinioDocumentStore:
    """Factory: mock for Phase 1, MinIO/Postgres for Phase 2."""
    if settings.storage_backend == "minio":
        return MinioDocumentStore(settings)
    return InMemoryDocumentStore(settings)
```

`k_app` imported `InMemoryDocumentStore` directly. `STORAGE_BACKEND` could not have made this suite Phase 2.

HTTP in the suite is `httpx.ASGITransport` against the FastAPI app with `doc_module.store` monkeypatched to that dict. There is no K server on a port.

### L2’s 93 citation GETs

`test_l2_citations_resolve_via_real_k` also takes `k_app`. It seeded via `store.upsert(...)` into the same dict, then `client.get("/api/v1/document/{id}")` on that ASGI client. Same in-memory store. Not a separately wired K process.

### What was already running (not used by K yet)

Block D verify compose from `FIX_PASS_D-E-G_2026-08-16.md` was already up:

```
block-d-verify-pg     Up (healthy)  0.0.0.0:5435->5432/tcp
block-d-verify-minio  Up            0.0.0.0:9000-9001->9000-9001/tcp
```

Health before any fixture change:

```
docker exec block-d-verify-pg pg_isready -U postgres
/var/run/postgresql:5432 - accepting connections

psql \dt on block_d_verify:
 public | secrets | table
 public | tenants | table
(no documents table)

GET http://localhost:9000/minio/health/live → 200
MinIO buckets: ['block-d-verify']  (0 objects)
```

No K metadata table, no K objects. D/E pipeline documents were not present to read back.

**Part A conclusion:** last session’s “7 passed” and “93/93 citation GETs through real K” were Phase 1 logic against a mock store. Proceeded to Part B.

---

## 5.2 Part B — Wire K’s suite to real Postgres/MinIO

Did not start a new compose stack; used the already-running Block D verify services (`services/block-d-storage/docker-compose.yml`: `block-d-verify-pg` on host 5435, `block-d-verify-minio` on host 9000). Credentials are the compose file’s verify defaults, not values from `.env`.

### What changed

1. **`k_app` now uses `create_document_store` with `storage_backend=minio`**, pointed at:
   - MinIO `localhost:9000`, bucket `documents` (created on the same MinIO instance as `block-d-verify`)
   - Postgres `localhost:5435` / database `block_d_verify`
   - Fails setup if the factory still returns `InMemoryDocumentStore`
2. **`MinioDocumentStore`**: `ensure_schema` (`documents` table), `ensure_bucket`, and `upsert` that writes metadata to Postgres and the body to MinIO. Tests `await store.upsert(...)`.
3. **Block Z seed** when the table is empty: `backend/tests/fixtures/block_z/corpus_docs.json` (60 docs) written into the real store before tests run.

ACL remains `MockACLChecker`. K1’s grant/revoke/`call_count` API has no Block C equivalent in this session’s declared dependencies. **Phase 2 here is storage, not live ACL compile.** Named, not expanded.

### Proof data existed before K1–K3 assertions ran

First fixture setup (attempt 2, after datetime bind fix):

```
[BLOCK K] Phase 2 store=MinioDocumentStore minio=localhost:9000 pg=localhost:5435/block_d_verify rows_before_seed=0
[BLOCK K] seeded Block Z corpus; rows_after_seed=60
```

Subsequent tests saw persisted rows (`rows_before_seed=61` … `64`) — that cannot happen with a per-test dict.

After K1–K3, independently queried the running containers (not the Python dict):

```
SELECT tenant_id, COUNT(*) FROM documents GROUP BY tenant_id;

   tenant_id   | count
---------------+-------
 tenant_f_test |    59
 tenant-k      |     5
 tenant_other  |     1

MinIO buckets: ['block-d-verify', 'documents']
documents_bucket_objects 65
```

59+1 Block Z tenants + 5 K-suite docs = 65 rows and 65 MinIO objects.

### Attempts

| Attempt | Result |
|---------|--------|
| 1 | Setup ERROR: asyncpg `timestamptz` rejected ISO strings from Block Z (`expected datetime, got str`). Table created, 0 rows. |
| 2 | Parse ISO timestamps in `upsert`. **K 7 passed.** |

Stopped at 2 of 3.

---

## 5.3 Part C — Re-run, labeled Phase 2

### K1–K3 (Phase 2)

```
python -m pytest tests/test_block_k_signoff.py -v --tb=short -s
```

```
test_k1_allow_then_deny_after_revoke PASSED   store=MinioDocumentStore … rows_before_seed=0 then seeded 60
test_k1_missing_token_401 PASSED              rows_before_seed=61
test_k1_not_found_404 PASSED                  rows_before_seed=61
test_k2_streams_large_document PASSED         rows_before_seed=61
test_k2_small_document_not_streamed PASSED    rows_before_seed=62
test_k3_structure_fidelity PASSED             rows_before_seed=63
test_k3_redacts_hidden_fields_for_non_owner PASSED  rows_before_seed=64
====================== 7 passed, 174 warnings in 21.80s =======================
```

| ID | Architecture criterion | Phase | Result |
|----|------------------------|-------|--------|
| K1 | ACL re-check, 100% post-revoke deny | **2 (storage)** | **PASS** — bodies read from MinIO; ACL checker still in-process mock |
| K2 | Stream >10MB, bounded memory | **2** | **PASS** — large object streamed from MinIO |
| K3 | Structure fidelity 100% | **2** | **PASS** |

### L2 (Phase 2 K storage)

**Cost check-in before the live run:** 31 OpenRouter chat completions (same ≥30 sampled answers as before). Real quota, not a local LLM.

Actual: **31** billed completions. No retries.

```
python -m pytest tests/test_block_l_architecture.py::test_l2_citations_resolve_via_real_k -v --tb=short -s
```

```
[BLOCK K] Phase 2 store=MinioDocumentStore minio=localhost:9000 pg=localhost:5435/block_d_verify rows_before_seed=65
L2 sampled_answers=31 citation_gets_ok=93
PASSED
================= 1 passed, 241 warnings in 78.87s =================
```

After L2, Postgres showed `tenant-l-arch | 4` (3 public + secret) and MinIO `documents_bucket_objects 69`. Citation GETs resolved `document_id`s that were stored in real Postgres+MinIO, not an in-memory dict.

Retrieval for the chat still uses `StubToolbox` (ACL-filtered hits). That is unchanged and not a K-storage mock. L1/L3/L4 were not re-run (they do not depend on K’s storage backend).

### Unrelated issues noticed, not fixed

- `StubToolbox` has no `signals_url`; fire-and-forget activity ingest still logs `AttributeError` (non-blocking).
- `Settings` declares `storage_backend` twice (`config.py` ~72 and ~461). Fixture sets the attribute in process; env-alias behavior of the duplicate is untrusted.
- K Phase 2 ACL is still `MockACLChecker` (Block C `/acl/compile` not in this session’s dependency list).

---

## 5.4 Updated overall D–L status (explicit Phase 1 / Phase 2)

D–J from prior passes, not re-run this session.

| Block | Phase 1 (mock / test double) | Phase 2 (real infra) | Notes |
|-------|------------------------------|----------------------|--------|
| D Storage | PASS (prior) | **PASS** (prior) | Same verify compose used here (`block-d-verify-pg` :5435, `block-d-verify-minio` :9000) |
| E Chunking | PASS (prior) | **PASS** (prior) | |
| F Lexical | PASS (prior) | **PASS** (prior) | |
| G Vector | PASS (prior) | **PASS** (prior) | |
| H Graph | PASS (prior) | **PASS** (prior) | |
| I Signals | PASS (prior) | **PASS** (prior) | |
| J Federator | PASS (prior) | **PASS** (prior) | |
| K Reader | PASS (prior session, in-memory) | **PASS** (this session, 7/7) | MinIO+Postgres. ACL still mock |
| L Orchestrator | File-named 6/6; L1/L3/L4 architecture PASS (prior) | **L2 PASS** this session against Phase 2 K (31 OpenRouter calls, 93/93 K GETs) | Chat adapter unchanged; L2 now reads real object storage |
| Q (K+L) | Prior “PASS” overstated K Phase 2 | K Phase 2 + L2-via-real-K now hold | Independent §24 reviewer still required |

**Bottom line:** Last session’s K “7 passed” and L2 “93/93” were Phase 1. This session pointed `k_app` at Block D verify Postgres+MinIO, seeded Block Z, and re-ran. K1–K3 **PASS Phase 2 (storage)**. L2 **PASS** against that same real store (31 billed completions). ACL is still an in-process mock.

Stopped here. No `SIGNOFF.md` edits, no M/N/O, no commit, no push.
