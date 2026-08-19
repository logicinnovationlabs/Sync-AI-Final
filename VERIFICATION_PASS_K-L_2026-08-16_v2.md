# Independent Verification Pass v2 — Blocks K & L (collection fix + re-run)

**Date:** 2026-08-16  
**Type:** Narrow fix (dependency conflict only) + re-verify + diagnostic reporting.  
**This file is not `SIGNOFF.md`.** The original `VERIFICATION_PASS_K-L_2026-08-16.md` is left in place as the first-pass record.

**Commit tested:** `5ce77b1a97f3bf0ea0ba980282940f517e7ad911` (`Add: Block N completed and tested`)  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

Python:

```
C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\python.exe
3.14.0
```

No product code was changed. No LLM adapter was added. `SIGNOFF.md` was not touched.

---

## 6.1 Part A — Collection blocker

### What was actually installed vs pinned

| Package | `backend/pyproject.toml` | `backend/requirements.txt` (before) | Installed (before) |
|---------|---------------------------|--------------------------------------|--------------------|
| langgraph | `^0.2.0` → `>=0.2.0,<0.3.0` | `>=0.2` (no upper bound) | **1.2.2** (Roaming site-packages) |
| langchain-core | `^0.2.0` → `>=0.2.0,<0.3.0` | `>=0.2` (no upper bound) | **0.2.43** |
| langgraph-checkpoint | (transitive) | (transitive) | **4.1.1** |

`langgraph` 1.2.2 requires `langchain-core>=1.4.0,<2` and, via `langgraph-checkpoint` 4.1.1, does `Reviver(allowed_objects="core")`.  
`langchain-core` 0.2.43 `Reviver.__init__` parameters are `secrets_map, valid_namespaces, secrets_from_env, additional_import_mappings` — **no `allowed_objects`**.

That is the `TypeError` from the first K/L pass.

The pins were inconsistent in **two** ways:

1. **`requirements.txt` vs `pyproject.toml`:** Poetry `^0.2.0` forbids langgraph 1.x; pip `>=0.2` allows it. This environment is pip-installed, so 1.2.2 won.
2. **`requirements.txt` internally:** `langgraph>=0.2` can resolve to 1.2.2, which cannot run on `langchain-core>=0.2` as 0.2.43.

This is the same class of “pin vs installed” mismatch as G-fix-1. It is **not** a stale install of an otherwise-consistent pair.

### Compatible pair chosen

Repo code only imports `from langgraph.graph import END, START, StateGraph` (both copies of `graph.py`). That API exists on the 0.2 line.

PyPI `langgraph==0.2.76` requires:

- `langchain-core>=0.2.43,<0.4.0` (with a list of excluded 0.3.x versions)
- `langgraph-checkpoint>=2.0.10,<3.0.0`

That pair matches `pyproject.toml`’s already-declared `^0.2.0`. The other candidate (`langgraph` 1.2.2 + `langchain-core` ≥1.4) is a **major** `langchain-core` jump; nothing in this repo imports `langchain-core` directly, but it would also rewrite the Poetry pin from 0.2 to 1.x. That was not needed to unblock collection.

**Fix (pins + reinstall), attempt 1 of 3 — succeeded:**

`.bak` taken:

- `backend/requirements.txt.bak`
- `assistant_orchestrator/requirements.txt.bak`

`backend/pyproject.toml` was **not** edited (`langgraph = "^0.2.0"` / `langchain-core = "^0.2.0"` already describe this pair).

`backend/requirements.txt` and `assistant_orchestrator/requirements.txt`:

```
langgraph>=0.2.76,<0.3
langchain-core>=0.2.43,<0.3
```

Then:

```
python -m pip install "langgraph==0.2.76" "langchain-core==0.2.43"
python -m pip uninstall -y langgraph-prebuilt
```

`langgraph-prebuilt` 1.1.0 was a leftover of langgraph 1.2.2 (`requires langchain-core>=1.3.1`). It is not imported by this repo.

After install:

```
langgraph 0.2.76
langchain-core 0.2.43
langgraph-checkpoint 2.1.2
import_ok True True StateGraph
```

pip also warned `langchain-openai 0.1.14 requires openai<2.0.0,>=1.32.0, but you have openai 2.50.0`. Not touched (out of scope; does not block K/L collection).

### Proof both signoff suites collect

```
cd backend
$env:PYTHONPATH = "D:\PROJECTS\A sync Ai final\backend"
python -m pytest tests/test_block_k_signoff.py --collect-only -q
python -m pytest tests/test_block_l_signoff.py --collect-only -q
```

```
tests/test_block_k_signoff.py::test_k1_allow_then_deny_after_revoke
tests/test_block_k_signoff.py::test_k1_missing_token_401
tests/test_block_k_signoff.py::test_k1_not_found_404
tests/test_block_k_signoff.py::test_k2_streams_large_document
tests/test_block_k_signoff.py::test_k2_small_document_not_streamed
tests/test_block_k_signoff.py::test_k3_structure_fidelity
tests/test_block_k_signoff.py::test_k3_redacts_hidden_fields_for_non_owner
7 tests collected in 0.02s
K_COLLECT_EXIT=0

tests/test_block_l_signoff.py::test_l_health
tests/test_block_l_signoff.py::test_l1_chat_requires_matching_tenant
tests/test_block_l_signoff.py::test_l2_chat_streams_ndjson
tests/test_block_l_signoff.py::test_l3_cross_tenant_session_denied
tests/test_block_l_signoff.py::test_l4_chat_persists_session_in_docker_postgres
tests/test_block_l_signoff.py::test_l_empty_prompt_rejected
6 tests collected in 0.04s
L_COLLECT_EXIT=0
```

Part A done. Collection no longer raises `Reviver(allowed_objects=...)`.

---

## 6.2 Part B — Re-run K1–K3 and L1–L4

Config names only (values never printed):

```
ANTHROPIC_API_KEY=UNSET
AZURE_OPENAI_API_KEY=UNSET
LLM_PROVIDER=UNSET
provider_is_fake True
anthropic_api_key_present False
azure_openai_api_key_present False
storage_backend_is_mock True
```

Full platform stack was not started. K’s architecture suite injects `InMemoryDocumentStore` + `MockACLChecker`. For L, only `snyq_postgres` was started from `backend/docker-compose.yml` (session store). Redis `:6379` was already Block E’s container; it was reused, not replaced.

### Block K

**Phase reached:** Phase 1 (in-memory store + mock ACL). Phase 2 (MinIO + HTTP ACL) is not what this suite exercises. MinIO `:9000` was up from Block D and unused.

**Command:**

```
python -m pytest tests/test_block_k_signoff.py -v --tb=short -s
```

```
collected 7 items
...
FAILED tests/test_block_k_signoff.py::test_k1_allow_then_deny_after_revoke
FAILED tests/test_block_k_signoff.py::test_k1_missing_token_401
FAILED tests/test_block_k_signoff.py::test_k1_not_found_404
FAILED tests/test_block_k_signoff.py::test_k2_streams_large_document
FAILED tests/test_block_k_signoff.py::test_k2_small_document_not_streamed
FAILED tests/test_block_k_signoff.py::test_k3_structure_fidelity
FAILED tests/test_block_k_signoff.py::test_k3_redacts_hidden_fields_for_non_owner
====================== 7 failed, 201 warnings in 17.06s =======================
```

Every failure is the same, before any ACL/stream/structure assertion:

```
tests\test_block_k_signoff.py:47: in test_k1_allow_then_deny_after_revoke
    resp_a = await client.get(
E   TypeError: 'Response' object can't be awaited
```

`k_app` yields a **sync** `fastapi.testclient.TestClient`. The tests `await client.get(...)`. `TestClient.get` already returns a `Response`. An unused `k_app_async` fixture exists in `backend/tests/conftest.py` (`httpx.AsyncClient`) and is not wired to these tests.

That is **not** the langgraph conflict. It is a test-fixture mismatch. Not fixed this session (out of scope).

| ID | Architecture criterion | Result | Evidence |
|----|------------------------|--------|----------|
| K1 | ACL re-check: revoke mid-session → 100% post-revoke deny, no cache | **FAIL** | `test_k1_allow_then_deny_after_revoke` never issued a GET; `TypeError: 'Response' object can't be awaited` |
| K2 | Stream >10MB, bounded memory, no timeout/OOM | **FAIL** | `test_k2_streams_large_document` same TypeError |
| K3 | Structure fidelity 100% | **FAIL** | `test_k3_structure_fidelity` same TypeError |

K is **not** reachable as a working `GET /api/v1/document/{id}` from this suite, so L2 cannot be scored against real K.

### Block L — cost check-in (before the run)

No paid key is configured (`provider_is_fake True`, Anthropic/Azure key names absent). The orchestrator does not call a chat LLM (Part C).  

**Estimate:** the file suite makes 4 `POST /api/v1/assistant/orchestrator/chat` requests + one empty-prompt 422. **0 billed completions.** Architecture L1≥20 + L2≥30 do not exist as tests, so they were not run and did not burn quota.

**Actual billed calls this session: 0.**

### Block L — what was brought up

```
docker compose -f docker-compose.yml up -d postgres
snyq_postgres   Up (healthy)   0.0.0.0:5432->5432/tcp
```

App / redis / qdrant from that compose file were not started.

### File suite result (IDs do **not** match architecture L1–L4)

```
python -m pytest tests/test_block_l_signoff.py -v --tb=short -s
```

```
tests/test_block_l_signoff.py::test_l_health PASSED
tests/test_block_l_signoff.py::test_l1_chat_requires_matching_tenant PASSED
tests/test_block_l_signoff.py::test_l2_chat_streams_ndjson PASSED
tests/test_block_l_signoff.py::test_l3_cross_tenant_session_denied PASSED
tests/test_block_l_signoff.py::test_l4_chat_persists_session_in_docker_postgres PASSED
tests/test_block_l_signoff.py::test_l_empty_prompt_rejected PASSED
================= 6 passed, 170 warnings in 281.20s (0:04:41) =================
```

Those six passes are real for **what those tests assert** (health, tenant 403, NDJSON stream, cross-tenant session, Postgres persist, empty prompt 422). They are **not** architecture L1–L4.

### Architecture L1–L4

| ID | Architecture criterion | Result | Evidence |
|----|------------------------|--------|----------|
| L1 | Restricted principal, ≥20 attempts, 0 leaks **into the prompt** (prompt-log inspection) | **FAIL** | No prompt-log red-team suite. File `test_l1_*` is tenant-mismatch 403 (passed). There is no LLM prompt (Part C); a “pass” here would be vacuously testing a missing mechanism |
| L2 | ≥30 answers, 100% citations resolve via **real Block K** `document_id` | **FAIL** | No ≥30-answer suite. File `test_l2_*` is NDJSON streaming (passed). K1–K3 FAIL, so citations cannot be proven through K. Citations in `response_generator` are copied from search-hit snippets, not a K round-trip check |
| L3 | Adversarial over-search → 100% terminate within configured max tool-call rounds | **FAIL** | No max-rounds config or adversarial suite. File `test_l3_*` is session isolation (passed). Graph is a fixed 4-node DAG (always terminates) — that is not the specified criterion |
| L4 | Swap `LlmProvider` via config only, 0 code changes, existing tests still pass | **FAIL** | No `LlmProvider` type. `LLM_PROVIDER` selects an **embedding** fake/gemini path, not a chat adapter. File `test_l4_*` is Postgres session persist (passed) |

**Phase reached for L:** Phase 1 only (fake LLM provider, no paid key). Phase 2 was not reachable.

---

## 6.3 Part C — What Block L actually implements

Investigated `backend/app/services/assistant/` and `assistant_orchestrator/` (duplicate trees). No new code.

### LLM adapter

**There is no LLM adapter/client on the orchestrator path.** Grep for `ChatModel`, `llm`, `adapter`, `planner`, `prompt assembl` in both trees returns no chat-provider implementation.

`response_generator` is entirely template-based:

```345:378:backend/app/services/assistant/core/graph.py
    async def response_generator(self, state: OrchestratorState) -> OrchestratorState:
        intent = state.get("intent")
        hits = state.get("ranked_hits") or []
        if intent == Intent.CHAT.value:
            text = (
                "I can search your tenant corpus, open a specific document, "
                "or answer with citations from retrieved sources. "
                "Ask me to find something or open a document."
            )
            return {**state, "response_text": text, "citations": []}
        ...
        text = prefix + ":\n" + "\n".join(lines)
        return {**state, "response_text": text, "citations": citations}
```

`LLM_PROVIDER` in `backend/app/core/config.py` is consumed by `backend/app/services/embedding.py` (`FakeEmbeddingProvider` / Gemini / etc.), not by the assistant graph.

### Are architecture L1 and L4 meaningfully testable?

**No.**

- **L1** inspects a model **prompt** for leaked restricted content. There is no prompt and no model call. The file-named `test_l1` passing (403 on tenant mismatch) is unrelated. Reporting L1 as PASS because “nothing leaked into a prompt that was never built” would be a false pass.
- **L4** requires swapping an `LlmProvider` implementation via config. That interface does not exist for chat. Swapping `LLM_PROVIDER=fake` does not exercise a chat adapter.

### Planner / tool router / multi-step reasoning

| Architecture scope item | Present? | What exists |
|-------------------------|----------|-------------|
| Planner | **Heuristic only** | `classify_intent()` regex: SEARCH / READ / CHAT. Comment: “Heuristic only — does not inspect ACL.” |
| Tool router | **Hard-coded fan-out** | SEARCH always fires lexical + vector + signal_lookup in parallel. READ calls `read_document` if a blob id is present. No LLM-chosen tool sequence |
| Multi-step reasoning | **Fixed DAG, one optional extra hop** | `intent_router → parallel_searcher → personalized_ranker → response_generator → END`. If search confidence &lt; 0.6, one extra `read_document` on the top hit. No loop, no max-round counter |
| Citation capture | **Present, template-level** | Top 5 hits become `{document_id, quote, score}` from snippets. Not verified against K |
| Prompt assembly with ACL-safe context | **Absent** | ACL bytes are forwarded on tool HTTP calls (`SearchToolbox`); they are not assembled into an LLM prompt |
| LLM adapter | **Absent** | See above |

---

## 6.4 Part D — Block Q status

Q has no scope/criteria table of its own. Per the architecture tracking line, Q **is** “K and L integrated,” which this pass treats as: **K1–K3 all pass for real AND L1–L4 all pass for real, with L2 as the K→L proof.**

| Required for Q PASS | This session |
|---------------------|--------------|
| K1 | **FAIL** |
| K2 | **FAIL** |
| K3 | **FAIL** |
| L1 | **FAIL** (criterion not implemented; no LLM prompt) |
| L2 | **FAIL** (no real-K citation suite; K itself FAIL) |
| L3 | **FAIL** (criterion not implemented) |
| L4 | **FAIL** (no `LlmProvider`) |

**Q is not PASS.** It is blocked by every K row and every architecture L row. L2 in particular cannot prove K→L integration while K’s own suite never successfully `GET`s a document.

**Discrepancy:** the §24 block-tracking table currently records “Block Q — Integration of K L — Done (13/8/2026).” That does not match this session: K1–K3 and architecture L1–L4 have still never passed once. Same class of discrepancy as D4’s pgcrypto gap. Not resolved in `SIGNOFF.md` or the tracking table here.

There is still no Q folder, Q test suite, or Q `SIGNOFF.md`. That absence is expected given Q has no criteria table; it is not a missing suite to hunt for.

---

## 6.5 Updated overall D–L status

Phase 2 = real infra for that block’s store/API (not mock). Official signoff still needs an independent reviewer. D–J rows are from prior passes, not re-run here.

| Block | Phase 1 (mock) | Phase 2 (real infra) | Notes |
|-------|----------------|----------------------|--------|
| D Storage | PASS (prior) | **PASS** (prior fix pass) | |
| E Chunking | PASS (prior) | **PASS** (prior fix pass) | |
| F Lexical | PASS (prior) | **PASS** (prior fix pass) | |
| G Vector | PASS (prior) | **PASS** (prior fix pass) | |
| H Graph | PASS (prior) | **PASS** (prior verification) | |
| I Signals | PASS (prior) | **PASS** (prior verification) | |
| J Federator | PASS (prior) | **PASS** (prior fix pass) | |
| K Reader | **FAIL** — suite now **collects** and **runs**; all 7 tests `TypeError: 'Response' object can't be awaited` | **Not reached** | In-memory fixtures only; not a langgraph issue |
| L Orchestrator | File-named tests **6 passed** (tenant/NDJSON/session/Postgres). Architecture L1–L4 **FAIL** | **Not reached** | Fake LLM; 0 billed calls; no chat adapter |
| Q (K+L integration) | **Not PASS** | **Not PASS** | Function of K1–K3 and L1–L4; tracking table “Done” does not match |

**Bottom line:** the collection blocker is fixed (`langgraph==0.2.76` + `langchain-core==0.2.43`). Architecture **K1–K3 FAIL** on a TestClient/`await` mismatch (not fixed). Architecture **L1–L4 FAIL** because those criteria are not what the file suite tests, and the LLM adapter they assume is not implemented. **Q is not done.**

Stopped here. No further fixes, no `SIGNOFF.md` edits, no commit, no Blocks M/N/O.
