# Independent Verification Pass — Blocks K & L

**Date:** 2026-08-16  
**Type:** Read-and-report only. This file is not `SIGNOFF.md`. No criteria were marked in any `SIGNOFF.md`. No product or test code was edited.

---

## Repo / branch

Working folder `D:\PROJECTS\A sync Ai final`:

```
On branch Pratham
5ce77b1a97f3bf0ea0ba980282940f517e7ad911 Add: Block N completed and tested
origin	https://github.com/logicinnovationlabs/Sync-AI-Final.git
```

**Commit tested:** `5ce77b1` (`5ce77b1a97f3bf0ea0ba980282940f517e7ad911`)

Python actually used:

```
C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\python.exe
3.14.0 (tags/v3.14.0:ebf955d, Oct  7 2025, 10:15:03) [MSC v.1944 64 bit (AMD64)]
```

Architecture doc `Glean Arch made by Glean v1.3.1` is not in this tree. Criterion IDs below are taken from the verification prompt (K1–K3, L1–L4), which states they are identical in v1.3 and v1.3.1.

There is no `services/block-k-*` or `services/block-l-*`. K and L live in the backend monolith (`backend/app/api/v1/document.py`, `backend/app/services/document_reader/`, `backend/app/services/assistant/`) plus a duplicate standalone tree `assistant_orchestrator/`. That matches the prompt’s §29 note (modules-in-one-backend). Full-platform compose was not started (§24 rule 1).

---

## Ground truth before this pass

Containers already up from prior D–J work (not started here):

```
NAMES                              STATUS                       PORTS
block-f-opensearch-test            Up (healthy)                 0.0.0.0:9201->9200/tcp
block-i-postgres-test              Up (healthy)                 0.0.0.0:15433->5432/tcp
block-h-test-neo4j                 Up (healthy)                 0.0.0.0:7475->7474/tcp, 0.0.0.0:7688->7687/tcp
block-g-test-redis                 Up (healthy)                 0.0.0.0:6381->6379/tcp
block-g-test-qdrant                Up (healthy)                 0.0.0.0:6335->6333/tcp
block-e-chunking-celery-worker-1   Up
block_e_postgres                   Up (healthy)                 0.0.0.0:5433->5432/tcp
block-e-chunking-redis-1           Up (healthy)                 0.0.0.0:6379->6379/tcp
block-d-verify-pg                  Up (healthy)                 0.0.0.0:5435->5432/tcp
block-d-verify-minio               Up                           0.0.0.0:9000-9001->9000-9001/tcp
```

Host ports at start of this pass: `5432` free, `6379` in use (Block E redis), `8000` free, `9000` in use (Block D MinIO). Backend compose (`snyq_postgres` / `snyq_app`) was **not** brought up: K’s architecture suite injects an in-memory store; L’s architecture suite never imported far enough to need Postgres.

---

## Config names (values never printed)

Process-env check (SET/UNSET only):

```
ANTHROPIC_API_KEY=UNSET
AZURE_OPENAI_API_KEY=UNSET
OPENAI_API_KEY=UNSET
GEMINI_API_KEY=UNSET
OPENROUTER_API_KEY=UNSET
LLM_PROVIDER=UNSET
EMBEDDING_PROVIDER=UNSET
STORAGE_BACKEND=UNSET
ACL_BACKEND=UNSET
```

`backend/.env` exists (not opened). Settings loaded by name only:

```
llm_provider_present True
provider_is_fake True
anthropic_api_key_present False
azure_openai_api_key_present False
storage_backend_is_mock True
acl_backend_is_mock True
storage_backend_is_minio False
```

Env var **names** the config expects: `LLM_PROVIDER` (aliases `EMBEDDING_PROVIDER`, `llm_provider`); `ANTHROPIC_API_KEY`; `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_KEY`; `STORAGE_BACKEND`; `ACL_BACKEND`. Template default in `backend/.env.example` is `LLM_PROVIDER=fake`. `docker-compose.signoff.yml` also sets `LLM_PROVIDER: fake`.

---

## Shared import failure (K signoff + L signoff + 4 of 5 L verify scripts)

Installed packages:

```
langgraph 1.2.2   (C:\Users\Ishu Raj\AppData\Roaming\Python\Python314\site-packages)
langchain-core 0.2.43  (C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages)
```

Repo pin: `langgraph>=0.2` and `langchain-core>=0.2` (`backend/requirements.txt`). Importing `langgraph.graph` raises:

```
File "...\langgraph\checkpoint\serde\jsonplus.py", line 47, in <module>
    LC_REVIVER = Reviver(allowed_objects="core")
TypeError: Reviver.__init__() got an unexpected keyword argument 'allowed_objects'
```

`backend/app/main.py` always imports assistant routes, which import `langgraph`. **K’s signoff fixture `k_app` therefore cannot construct a TestClient.** Not fixed this session.

---

## Block K — Document Reader

**Commit:** `5ce77b1`  
**Code:** `backend/app/api/v1/document.py` (`GET /api/v1/document/{doc_id}`), `backend/app/services/document_reader/`  
**Architecture suite:** `backend/tests/test_block_k_signoff.py`  
**Phase reached:** **Phase 1 attempted, not completed.** The signoff suite monkey-patches `InMemoryDocumentStore` + `MockACLChecker` (`backend/tests/conftest.py` fixture `k_app`). `STORAGE_BACKEND` is mock; tests never exercise `MinioDocumentStore`. MinIO `:9000` was up from Block D and was **not** used. Phase 2 (real object store + real ACL HTTP) was not reachable through the existing suite.

### Architecture criteria (K1–K3)

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| K1 | ACL re-check: revoke mid-session, 100% post-revoke deny, no cached permission | **FAIL** | `test_k1_allow_then_deny_after_revoke` ERROR at `k_app` setup; 0 assertions ran |
| K2 | Stream document >10MB, bounded memory, no timeout/OOM | **FAIL** | `test_k2_streams_large_document` ERROR at `k_app` setup; 0 assertions ran |
| K3 | Structure fidelity 100% (headings/tables/code blocks) | **FAIL** | `test_k3_structure_fidelity` ERROR at `k_app` setup; 0 assertions ran |

### Command

```
cd backend
$env:PYTHONPATH = "D:\PROJECTS\A sync Ai final\backend"
python -m pytest tests/test_block_k_signoff.py -v --tb=short -s
```

```
collected 7 items

tests/test_block_k_signoff.py::test_k1_allow_then_deny_after_revoke ERROR
tests/test_block_k_signoff.py::test_k1_missing_token_401 ERROR
tests/test_block_k_signoff.py::test_k1_not_found_404 ERROR
tests/test_block_k_signoff.py::test_k2_streams_large_document ERROR
tests/test_block_k_signoff.py::test_k2_small_document_not_streamed ERROR
tests/test_block_k_signoff.py::test_k3_structure_fidelity ERROR
tests/test_block_k_signoff.py::test_k3_redacts_hidden_fields_for_non_owner ERROR

======================= 59 warnings, 7 errors in 17.48s =======================
```

Full traceback (identical for all 7; first test):

```
___________ ERROR at setup of test_k1_allow_then_deny_after_revoke ____________
tests\conftest.py:193: in k_app
    fastapi_app = _get_app()
tests\conftest.py:157: in _get_app
    from app.main import app
app\main.py:25: in <module>
    from app.services.assistant.api import routes as assistant_routes
app\services\assistant\api\__init__.py:1: in <module>
    from .routes import create_app, router
app\services\assistant\api\routes.py:21: in <module>
    from app.services.assistant.core.graph import OrchestratorGraph, default_acl_from_claims
app\services\assistant\core\__init__.py:1: in <module>
    from .graph import OrchestratorGraph, build_orchestrator_graph
app\services\assistant\core\graph.py:11: in <module>
    from langgraph.graph import END, START, StateGraph
...\langgraph\checkpoint\serde\jsonplus.py:47: in <module>
    LC_REVIVER = Reviver(allowed_objects="core")
E   TypeError: Reviver.__init__() got an unexpected keyword argument 'allowed_objects'
```

### Second suite in repo (does **not** implement architecture K1–K3)

`tests/test_blocks/test_block_k.py` is `@pytest.mark.provisional`. IDs collide with architecture but measure different things, against **`POST /api/v1/read`** (Block Z in-process mock), not `GET /api/v1/document/{id}`:

| Test name | What it actually asserts |
|-----------|--------------------------|
| `test_k1_read_completeness` | body/title match fixture `doc-roadmap` |
| `test_k2_acl_on_read` | 403 on `doc-restricted` |
| `test_k3_latency` | p95 ≤ baseline (default 300ms) |

First run of this file (inherited `USE_REAL_SERVICES` SET from the prior J Phase 2 session) hit `127.0.0.1:8000` and failed `ConnectionRefusedError` on `POST /oauth/token`. Second run with that flag **unset** (Phase 1 default documented in root `pytest.ini`):

```
python -m pytest tests/test_blocks/test_block_k.py tests/test_blocks/test_block_l.py -v --tb=short -s
============================== 7 passed in 1.26s ==============================
```

Those 3 K passes are **Phase 1 mock-only** and **are not architecture K1–K3**. They are not counted as PASS in the table above.

---

## Block L — Assistant Orchestrator

**Commit:** `5ce77b1`  
**Code:** `backend/app/services/assistant/` (mounted on the monolith) and duplicate `assistant_orchestrator/`  
**Live chat path in signoff tests:** `POST /api/v1/assistant/orchestrator/chat` (not architecture `POST /api/v1/chat`)  
**Phase reached:** **Phase 1 only, and the architecture-named suite did not complete.** Reasons Phase 2 was not reachable:

1. `provider_is_fake True`; `anthropic_api_key_present False`; `azure_openai_api_key_present False`.
2. `OrchestratorGraph.response_generator` is a **template** over search hits. There is no `LlmProvider` chat adapter and no prompt-log inspection path.
3. L2 requires real Block K. K’s architecture suite never ran; L’s HTTP toolbox defaults to stub/localhost, and `assistant_orchestrator/tests/_stub_backends.py` fakes `GET /api/v1/document/{id}`.

### §4 cost estimate (before any live call)

| Source | Chat/completion count if executed | Billed LLM? |
|--------|-------------------------------------|-------------|
| Architecture L1 (≥20 red-team) + L2 (≥30 answers) + L3 multi-turn | **Suite does not exist.** Would be ≥50 live completions if it did and used a paid provider | N/A |
| `backend/tests/test_block_l_signoff.py` | 4 `POST .../chat` + 1 empty-prompt 422 | No — graph does not call an LLM; provider is fake |
| `assistant_orchestrator/tests/verify_block_l_e2e_conversation.py` | 3 turns | No — stub backends; import failed before any turn |
| `verify_block_l_search_vs_read_switch.py` | 2 graph runs | No — import failed |
| `verify_block_l_multitenant_isolation.py` | 2 chats | No — import failed |
| `verify_block_l_acl_passthrough.py` | 5 tool HTTP calls, 0 LLM | No |
| Provisional `tests/test_blocks/test_block_l.py` | 13 `POST /api/v1/assistant/chat` to Block Z mock (1+1+10+1) | No |

**Estimate used this session: 0 billed LLM API calls.**  
**Actual billed calls this session: 0.**  
No live paid-provider run was started.

### Architecture criteria (L1–L4)

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| L1 | Restricted principal, ≥20 attempts, 0 leaks into the prompt (prompt-log inspection) | **FAIL** | No red-team/prompt-log suite. Closest file `test_block_l_signoff.py::test_l1_chat_requires_matching_tenant` is tenant-mismatch 403. That test ERROR at import (same `Reviver` TypeError). Response path has no LLM prompt |
| L2 | ≥30 answers, 100% citations resolve via real Block K `document_id` | **FAIL** | No ≥30-answer suite. Signoff `test_l2_chat_streams_ndjson` is NDJSON streaming, not citation resolution. K Phase 2 not up. Signoff ERROR at import |
| L3 | Adversarial over-search → 100% terminate within max tool-call rounds | **FAIL** | No max-rounds suite and no `max_tool_call` config. Graph is a fixed 4-node DAG. Signoff `test_l3_*` is cross-tenant session isolation. ERROR at import |
| L4 | Swap `LlmProvider` via config only, 0 code changes, existing tests still pass | **FAIL** | No `LlmProvider` type in assistant code. `LLM_PROVIDER` selects **embedding** fake/gemini/etc. Signoff `test_l4_*` is Postgres session persist. ERROR at import |

### Command — architecture-named suite

```
cd backend
$env:PYTHONPATH = "D:\PROJECTS\A sync Ai final\backend"
python -m pytest tests/test_block_l_signoff.py -v --tb=short -s
```

```
collected 6 items

tests/test_block_l_signoff.py::test_l_health ERROR
tests/test_block_l_signoff.py::test_l1_chat_requires_matching_tenant ERROR
tests/test_block_l_signoff.py::test_l2_chat_streams_ndjson ERROR
tests/test_block_l_signoff.py::test_l3_cross_tenant_session_denied ERROR
tests/test_block_l_signoff.py::test_l4_chat_persists_session_in_docker_postgres ERROR
tests/test_block_l_signoff.py::test_l_empty_prompt_rejected ERROR

======================= 60 warnings, 6 errors in 14.52s =======================
```

Traceback (identical for all 6):

```
tests\test_block_l_signoff.py:42: in l_client
    return TestClient(_get_app())
tests\conftest.py:157: in _get_app
    from app.main import app
... (same chain as K) ...
app\services\assistant\core\graph.py:11: in <module>
    from langgraph.graph import END, START, StateGraph
...\langgraph\checkpoint\serde\jsonplus.py:47: in <module>
    LC_REVIVER = Reviver(allowed_objects="core")
E   TypeError: Reviver.__init__() got an unexpected keyword argument 'allowed_objects'
```

Postgres `:5432` was never started: the suite never got past import. `test_l4_chat_persists_session_in_docker_postgres` therefore did not touch `control_plane`.

### Standalone `assistant_orchestrator/tests/verify_block_l_*.py`

These talk to **stub** backends (`_stub_backends.py`), not live K. They do not implement architecture L1–L4.

```
======== verify_block_l_acl_passthrough.py ========
... stub ASGI errors: RuntimeError: Unexpected message received: http.request ...
RESULT tool=lexical_search ok=False ... err=peer closed connection without sending complete message body ...
RESULT tool=vector_search ok=False ...
RESULT tool=kg_query ok=False ...
RESULT tool=read_document ok=False ...
RESULT tool=signal_lookup ok=False ...
FAIL
 - lexical_search: call failed peer closed connection without sending complete message body (received 0 bytes, expected 427)
 - vector_search: call failed peer closed connection without sending complete message body (received 0 bytes, expected 409)
 - kg_query: call failed peer closed connection without sending complete message body (received 0 bytes, expected 62)
 - read_document: call failed peer closed connection without sending complete message body (received 0 bytes, expected 344)
 - signal_lookup: call failed peer closed connection without sending complete message body (received 0 bytes, expected 109)
EXIT_CODE=1

======== verify_block_l_signal_boost.py ========
TypeError: Reviver.__init__() got an unexpected keyword argument 'allowed_objects'
EXIT_CODE=1

======== verify_block_l_search_vs_read_switch.py ========
TypeError: Reviver.__init__() got an unexpected keyword argument 'allowed_objects'
EXIT_CODE=1

======== verify_block_l_multitenant_isolation.py ========
TypeError: Reviver.__init__() got an unexpected keyword argument 'allowed_objects'
EXIT_CODE=1

======== verify_block_l_e2e_conversation.py ========
TypeError: Reviver.__init__() got an unexpected keyword argument 'allowed_objects'
EXIT_CODE=1
```

Checked-in `assistant_orchestrator/tests/evidence_block_l_final.txt` claims a prior `PASS` for ACL passthrough. This session’s run of the same script was **FAIL** (stub connection closed). Discrepancy only; file not edited.

### Second suite in repo (does **not** implement architecture L1–L4)

`tests/test_blocks/test_block_l.py` is `@pytest.mark.provisional`, against **`POST /api/v1/assistant/chat`** on the Block Z mock:

| Test name | What it actually asserts |
|-----------|--------------------------|
| `test_l1_citation_faithfulness` | citation quote appears in **fixture** document body |
| `test_l2_acl_safe_answers` | restricted fixture IDs not cited |
| `test_l3_latency` | p95 ≤ baseline (default 2000ms) |
| `test_l4_refuse_unauthorized` | empty citations or `refused` |

Phase 1 re-run: **4 passed** in the same 7-passed session as provisional K. Citations resolve via `fixture_loader.get_documents()`, **not** via Block K. Not counted as architecture L1–L4 PASS.

---

## Block Q

Searched the tree for `Block Q`, `block-q`, `block_q`, `test_block_q`. **No folder, no test suite, no `SIGNOFF.md`.** `backend/PROJECT_STRUCTURE.md` block table goes A–L with no Q row. Integration of K+L is not independently evidenced here. An integration claim and two blocks independently passing are not the same thing; in this pass **neither K nor L independently passed architecture criteria**, and Q is absent.

---

## SIGNOFF.md discrepancy (side by side; not resolved)

`SIGNOFF.md` files in this repo exist only for **D, E, F, G, H, I, J**.

| Location | What SIGNOFF.md claims | What this pass observed |
|----------|------------------------|-------------------------|
| `services/block-k-*/SIGNOFF.md` | **File does not exist** | Architecture K1–K3 **FAIL** (suite ERROR at import) |
| `services/block-l-*/SIGNOFF.md` | **File does not exist** | Architecture L1–L4 **FAIL** (no matching tests + suite ERROR) |
| Block Q `SIGNOFF.md` | **File does not exist** | No Q tests/folder |
| `backend/PROJECT_STRUCTURE.md` | `test_block_k.py` / `test_block_l.py` marked ✅ | Those files are **provisional** mocks with **different** K1–K3 / L1–L4 meanings; they passed Phase 1 after unsetting leftover `USE_REAL_SERVICES`. Architecture signoff files ERROR |
| `assistant_orchestrator/tests/evidence_block_l_final.txt` | ACL passthrough `PASS` / `EXIT_CODE=0` | Same script this session: **FAIL** / `EXIT_CODE=1` |

---

## Flagged findings (not fixed)

1. **`langgraph` 1.2.2 vs `langchain-core` 0.2.43** — `Reviver(allowed_objects=...)` TypeError. Blocks **all** monolith K/L signoff tests and 4/5 standalone L verify scripts. Pins are `>=0.2` with no upper bound.
2. **K cannot be imported without L** — `app.main` always imports assistant routes.
3. **Architecture IDs in `test_block_l_signoff.py` do not match §24 L1–L4** (tenant 403 / NDJSON / session isolation / Postgres persist).
4. **Architecture IDs in `tests/test_blocks/test_block_*.py` do not match §24** (and hit `/api/v1/read` and `/api/v1/assistant/chat`, not the architecture interfaces).
5. **No LLM chat provider in the orchestrator** — `response_generator` templates snippets; `LLM_PROVIDER` is an embedding switch. L1 prompt-log and L4 provider-swap cannot pass as specified until that exists.
6. **L2 cannot be Phase 2 while K’s suite is mock-injected `InMemoryDocumentStore`** even after the import error is gone, unless a different suite hits real K.
7. **`Settings.storage_backend` is declared twice** in `backend/app/core/config.py` (lines 72 and 446).
8. **`k_app` yields sync `TestClient` while tests `await client.get(...)`** — not reached this session because setup failed first.
9. **`make_bearer` in `backend/tests/conftest.py` encodes HS256**; `get_current_user` uses `token_service.validate_token` (RS256 path). Not reached.
10. Leftover **`USE_REAL_SERVICES` SET** from the J Phase 2 session made the first provisional K/L run hit `:8000`. Unset for a second run only; not written to any `.env`.

---

## Updated overall D–L status

Phase 2 = real infra for that block’s store/API (not mock). Official signoff still needs an independent reviewer. D–J rows are copied from `FIX_PASS_F-J_2026-08-16.md` / prior verification; **K and L are this session**.

| Block | Phase 1 (mock) | Phase 2 (real infra) | Notes |
|-------|----------------|----------------------|--------|
| D Storage | PASS (prior) | **PASS** (local compose PG `:5435` + MinIO; prior fix pass) | Hosted Supabase pgcrypto was not that path |
| E Chunking | PASS (prior) | **PASS** (local compose PG `:5433`; prior fix pass) | E2 wrapper is 30s mock-embed harness, not 10-min |
| F Lexical | PASS (prior) | **PASS** (OpenSearch 2.17.1 `:9201`; prior fix pass) | |
| G Vector | PASS (prior) | **PASS** (Qdrant 1.12.1 `:6335`; prior fix pass) | |
| H Graph | PASS (prior) | **PASS** (Neo4j 5.26 `:7688`; prior verification) | |
| I Signals | PASS (prior) | **PASS** (Postgres `:15433`; prior verification) | |
| J Federator | PASS (prior) | **PASS** (real F + G + H HTTP; prior fix pass) | Graph signals 404-degraded |
| K Reader | **FAIL** (architecture suite 7 ERROR at import). Separate provisional mock suite 3 passed with **different** K1–K3 | **Not reached** | In-memory store only in the architecture tests; import blocked by langgraph |
| L Orchestrator | **FAIL** (architecture L1–L4 not implemented; signoff 6 ERROR; 4/5 verify scripts ERROR; ACL passthrough FAIL). Provisional mock suite 4 passed with **different** L1–L4 | **Not reached** | `LLM_PROVIDER` is fake; no paid key; 0 billed calls; no real K for L2 |
| Q (K+L integration) | **Not found** | **Not found** | No folder, tests, or SIGNOFF |

**Bottom line:** D–J remain Phase 2 real-infra green on this machine and commit (from prior passes, not re-run here). **Architecture K1–K3 and L1–L4 are FAIL.** Block Q is absent. This report is not `SIGNOFF.md`.

Stopped here. No fixes, no `SIGNOFF.md` edits, no commit, no Blocks M/N/O.
