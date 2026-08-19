# Build Pass — Block K tenant-ID fix + Block L OpenRouter/Qwen chat adapter

**Date:** 2026-08-16  
**Type:** One narrow K fix (tenant resolution on the document route) + authorized L chat-adapter build + re-verify.  
**This file is not `SIGNOFF.md`.** `VERIFICATION_PASS_K-L_2026-08-16_v4.md` is unchanged as the pre-build record.

**Commit tested (HEAD, uncommitted work on top):** `5ce77b1a97f3bf0ea0ba980282940f517e7ad911` (`Add: Block N completed and tested`)  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

Python: `C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\python.exe` 3.14.0

`.env` / `backend/.env` were never opened. Names only: `OPENROUTER_API_KEY`, `QWEN_MODEL`, `GEMINI_API_KEY`, `LLM_CHAT_PROVIDER`. Values never printed.

No commits, no pushes, no `SIGNOFF.md` edits.

---

## 6.1 Part A — Block K tenant-ID mismatch

### Diagnose: which side was wrong

There is **platform-wide inconsistency** on tenant identifier shape. That was checked before touching code.

| Layer | `tenant_id` type / usage |
|-------|--------------------------|
| Block A issuance (`backend/app/api/v1/admin/tenant.py`, `scripts/seed_tenants.py`) | `uuid4()` into control-plane `Tenant` |
| Backend ORM `app.models.tenant.Tenant` | `PG_UUID(as_uuid=True)` |
| `tenant_resolver.resolve` | `UUID(tenant_id)` then SQL against that UUID column |
| Block D storage schema `001_create_tenants_table.sql` | `tenant_id VARCHAR(255) PRIMARY KEY` — slugs are valid |
| Block D router `tenant_router/models.py` | `tenant_id: str` |
| Content APIs (lexical / vector / embed) | local `get_tenant` returns the **JWT claim as `str`**, no UUID parse |
| Other signoff fixtures | H `"block-h-test"`, I `"block-i-test"`, F/J `"tenant_f_test"` / `"tenant_j_test"` (slugs); L/N use `uuid4()` |
| K signoff fixture | `"tenant-k"` (slug) |
| K document store | `Dict[tuple[str, str], ...]` keyed by string tenant_id |

So it is **not** “UUIDs everywhere, K fixture is the only outlier,” and it is **not** “slugs are valid in the control-plane resolver.” Two different contracts exist:

1. **Control-plane routing** (Block A `Tenant` row → Vault → tenant DB) is UUID-only. `UUID(...)` there matches the ORM column.
2. **Content keys** (document store, search, Block D VARCHAR, several block fixtures) are opaque strings, including slugs.

Relaxing `tenant_resolver.resolve` to accept `"tenant-k"` would be the wrong side: that function queries a UUID column. Changing K’s fixture to a UUID would also be the wrong side **for this 500**: even a well-formed UUID would then 404 (`TenantNotFoundError`) because `k_app` never seeds a control-plane row, and even a seeded row would inject a `TenantRouting` object into `store.get_metadata(tenant_id, ...)` because `get_tenant` returns routing, while `document.py` type-hinted `tenant_id: str`.

**The K 500 was a wiring bug on the document route**, not a fixture-format bug and not a resolver-too-strict bug.

`GET /api/v1/document/{id}` used `Depends(get_tenant)` from `app.api.deps` (control-plane UUID routing). Block K only needs the JWT `tenant_id` string as a store/ACL key — the same pattern lexical and vector already use.

### Fix (attempt 1 of 2 for the 500; attempt 2 for a follow-on that the 500 had hidden)

1. **`backend/app/api/v1/document.py`** — stop using `deps.get_tenant`. Extract `tenant_id` from the JWT as `str`. `HTTPBearer(auto_error=False)` so a missing token is **401**, not Starlette’s default **403**.
2. **`backend/app/services/document_reader/reader.py`** — after the 500 was gone, K1/K2/K3 hit `TypeError: build_document_payload() got an unexpected keyword argument 'doc_id'`. The route and the signoff tests already called a 6-arg streaming helper and a kwargs payload builder; `reader.py` still had an older 3-arg signature. Aligned `build_document_payload` / `stream_document_json` to that contract (stream concatenates to one JSON object with bounded chunk memory). This was not a tenant-ID change; it was unreachable until the 500 was removed.

`tenant_resolver.py` was **not** relaxed. The K fixture stayed `"tenant-k"`. Control-plane UUID routing is unchanged.

### Re-verify

```
python -m pytest tests/test_block_k_signoff.py -v --tb=short
```

**Attempt 1 (tenant wiring only):** UUID 500 gone. `test_k1_missing_token_401` PASSED, `test_k1_not_found_404` PASSED. Remaining 5 failed on `build_document_payload() got an unexpected keyword argument 'doc_id'`.

**Attempt 2 (payload/stream signatures):**

```
tests/test_block_k_signoff.py::test_k1_allow_then_deny_after_revoke PASSED
tests/test_block_k_signoff.py::test_k1_missing_token_401 PASSED
tests/test_block_k_signoff.py::test_k1_not_found_404 PASSED
tests/test_block_k_signoff.py::test_k2_streams_large_document PASSED
tests/test_block_k_signoff.py::test_k2_small_document_not_streamed PASSED
tests/test_block_k_signoff.py::test_k3_structure_fidelity PASSED
tests/test_block_k_signoff.py::test_k3_redacts_hidden_fields_for_non_owner PASSED
====================== 7 passed, 174 warnings in 17.24s =======================
```

| ID | Architecture criterion | Result | Evidence |
|----|------------------------|--------|----------|
| K1 | ACL re-check, 100% post-revoke deny | **PASS** | `test_k1_allow_then_deny_after_revoke` PASSED; missing token 401 and missing doc 404 also PASSED |
| K2 | Stream >10MB, bounded memory | **PASS** | `test_k2_streams_large_document` PASSED |
| K3 | Structure fidelity 100% | **PASS** | `test_k3_structure_fidelity` + redaction PASSED |

**Phase:** Phase 1 (in-memory store + mock ACL). Phase 2 MinIO was not in this session’s scope.

---

## 6.2 Part B — OpenRouter/Qwen chat adapter

Confirmed before writing: no `LlmProvider` / `ChatProvider` protocol existed. `LLM_PROVIDER` remains the **embedding** switch (`fake` / `gemini`). `response_generator` was a snippet template. `OPENROUTER_API_KEY` and `QWEN_MODEL` were config-only.

Surveyed precedents: `GeminiEmbeddingProvider` / `FakeEmbeddingProvider` / `EmbeddingService` in `backend/app/services/embedding.py`. Chat side mirrors that shape.

### What was built

| File | Change |
|------|--------|
| `backend/app/services/assistant/infrastructure/chat_provider.py` | **New.** `ChatProvider` protocol, `FakeChatProvider`, `OpenRouterChatProvider` (`openai.AsyncOpenAI`, `base_url` default `https://openrouter.ai/api/v1`, key from `settings.openrouter_api_key`, `model=` from `settings.qwen_model` — value never logged), `create_chat_provider()`, `ChatService`, `assemble_chat_messages()`, inspectable `PROMPT_LOG` |
| `backend/app/core/config.py` | `llm_chat_provider` (default `fake`), `openrouter_base_url`, `llm_max_tool_call_rounds` (default `2`) |
| `backend/app/services/assistant/core/graph.py` | `response_generator` calls `ChatService.generate()` on messages built **only** from the user prompt + `ranked_hits` (already ACL-filtered by retrieval). Citations still come from those `document_id`s. `tool_call_rounds` capped at `llm_max_tool_call_rounds`. Intent router / parallel search / ranker unchanged. |
| `backend/app/services/assistant/api/routes.py` | Final NDJSON event includes `llm_prompt`, `tool_call_rounds`, `chat_provider_name` |
| `backend/requirements.txt` + `backend/pyproject.toml` | `openai>=1.54.0,<2` (no prior pin; installed `openai==1.109.1`) |
| `backend/.env.example` | `LLM_CHAT_PROVIDER=fake`, `OPENROUTER_BASE_URL`, `LLM_MAX_TOOL_CALL_ROUNDS` |
| `backend/tests/test_block_l_architecture.py` | **New.** Architecture L1–L4 (not the tenant-403/NDJSON file suite) |

Config switch (L4): `LLM_CHAT_PROVIDER=fake` (default, no network) or `openrouter`. Independent of `LLM_PROVIDER` (embeddings). Graph does not hardcode a vendor; `create_chat_provider()` re-reads Settings unless a provider is pinned.

### Retrieval / ACL / citations / loop (checked, not patched)

- **L1 prompt contents:** `assemble_chat_messages` only inlines `ranked_hits`. The graph never fetches extra corpus at generation time. Upstream retrieval (federator / document reader) is the ACL filter; this session did not touch F/G/H/I/J. If those backends leak, that is still their bug — the adapter will not add unauthorized docs on its own.
- **L2 citations:** still the `document_id`s on `ranked_hits`, which L2 then `GET`s through real Block K.
- **L3:** the graph remains a fixed DAG (`intent_router → parallel_searcher → personalized_ranker → response_generator`). Max extra tool round is the search-vs-read document-reader fallback, now counted against `llm_max_tool_call_rounds` (default 2). No new planner loop was added.

Diff-level (tracked files): `9 files changed, 190 insertions(+), 61 deletions(-)` plus two untracked files (`chat_provider.py`, `test_block_l_architecture.py`).

---

## 6.3 Part C — Cost check-in, then L1–L4 for real

### Estimate (reported before the live run)

| Criterion | Planned live OpenRouter chat completions |
|-----------|------------------------------------------|
| L1 ≥20 red-team | 22 |
| L2 ≥30 answers | 31 |
| L3 adversarial multi-turn | 8 turns (one completion each) |
| L4 config swap | 0 (factory + fake path) |
| **Total** | **61** |

OpenRouter bills/limits per request the same way a direct provider key would. This is real quota, not a local container.

### Actual

Live run (after L4 + the existing file-named L suite had already passed offline):

```
python -m pytest tests/test_block_l_architecture.py::test_l1_prompt_log_redteam_no_restricted_leak \
  tests/test_block_l_architecture.py::test_l2_citations_resolve_via_real_k \
  tests/test_block_l_architecture.py::test_l3_adversarial_oversearch_respects_max_rounds \
  -v --tb=short -s
```

```
tests/test_block_l_architecture.py::test_l1_prompt_log_redteam_no_restricted_leak PASSED
tests/test_block_l_architecture.py::test_l2_citations_resolve_via_real_k L2 sampled_answers=31 citation_gets_ok=93
PASSED
tests/test_block_l_architecture.py::test_l3_adversarial_oversearch_respects_max_rounds L3 turns=8 max_rounds=2 tool_names_total=24
PASSED
================= 3 passed, 249 warnings in 185.00s (0:03:04) =================
```

**Actual billed chat completions: 61** (22 + 31 + 8). Matches the estimate. No extra retries.

L4 (no live calls), already run:

```
tests/test_block_l_architecture.py::test_l4_provider_swap_via_config_only PASSED
tests/test_block_l_architecture.py::test_l4_existing_fake_path_still_answers PASSED
```

Existing file-named suite (tenant 403 / NDJSON / session / Postgres — **not** architecture L1–L4) still passes with default `fake`:

```
tests/test_block_l_signoff.py — 6 passed
================= 8 passed, 175 warnings in 286.06s (0:04:46) =================
```
(8 = 2 L4 architecture + 6 file-named.)

| ID | Architecture criterion | Result | Evidence |
|----|------------------------|--------|----------|
| L1 | ≥20 prompt-log red-team; 0 restricted leaks into the prompt | **PASS** | 22 attempts; `SECRET_MARKER` / `doc-secret-titan` absent from `PROMPT_LOG` sent to OpenRouter |
| L2 | ≥30 answers; 100% citations resolve via real K `GET /api/v1/document/{id}` | **PASS** | 31 answers; 93 citation GETs 200 (3 hits × 31). Retrieval in this suite is an ACL-filtered stub (F/J not started this session); K HTTP is the real document route from Part A |
| L3 | Adversarial over-search terminates within max tool-call rounds | **PASS** | 8 turns, `max_rounds=2`, all `tool_call_rounds <= 2`; 24 tool names = 3 parallel tools × 8 (no extra unbounded loop) |
| L4 | Swap chat provider via config only | **PASS** | `LLM_CHAT_PROVIDER=fake` → `FakeChatProvider`; `openrouter` → `OpenRouterChatProvider`; existing fake tests still pass |

Non-blocking log noise during L1–L3: `StubToolbox` has no `signals_url`, so fire-and-forget activity ingest logged `AttributeError`. Tests still passed; ingest is daemon and must not fail the chat path.

---

## 6.4 Part D — Block Q

Q PASS = K1–K3 and L1–L4 all pass for real after Parts A–C, with L2 as the K→L proof.

**Q is PASS this session** (K1–K3 PASS; architecture L1–L4 PASS; L2 resolved 93/93 citations through real Block K GET). Independent §24 rule-1 reviewer signoff is still required; this report is not that signoff.

---

## 6.5 Updated overall D–L status

D–J from prior passes, not re-run this session.

| Block | Phase 1 (mock) | Phase 2 (real infra) | Notes |
|-------|----------------|----------------------|--------|
| D Storage | PASS (prior) | **PASS** (prior) | |
| E Chunking | PASS (prior) | **PASS** (prior) | |
| F Lexical | PASS (prior) | **PASS** (prior) | |
| G Vector | PASS (prior) | **PASS** (prior) | |
| H Graph | PASS (prior) | **PASS** (prior) | |
| I Signals | PASS (prior) | **PASS** (prior) | |
| J Federator | PASS (prior) | **PASS** (prior) | |
| K Reader | **PASS** (this session, 7/7 signoff) | **Not reached** | JWT tenant_id as string; payload/stream signatures aligned. Still in-memory store |
| L Orchestrator | File-named suite still 6/6. Architecture L1–L4 **PASS** against OpenRouter/Qwen | Live chat: **61** OpenRouter completions | `LLM_CHAT_PROVIDER` selects fake vs openrouter. Gemini still embeddings-only |
| Q (K+L integration) | **PASS** (consequence of K1–K3 + L1–L4) | Pending independent reviewer | Not written to `SIGNOFF.md` |

**Bottom line:** K’s 500 was the document route using control-plane UUID routing; content APIs already used the JWT string. K1–K3 now pass. Block L has a real OpenRouter/Qwen `ChatProvider` on the response path, selected by `LLM_CHAT_PROVIDER`, with fake retained as default. Architecture L1–L4 passed against that provider (61 billed calls). Q follows. Independent reviewer still has to sign §24.

Stopped here. No `SIGNOFF.md` edits, no M/N/O, no commit, no push.
