# Independent Verification Pass v3 — Block K test-client fix + Gemini re-check

**Date:** 2026-08-16  
**Type:** One narrow harness fix (`k_app`) + corrected Gemini diagnostic + re-verify.  
**This file is not `SIGNOFF.md`.** v2 stays as a record. No Gemini adapter was wired or built.

**Commit tested:** `5ce77b1a97f3bf0ea0ba980282940f517e7ad911` (`Add: Block N completed and tested`)  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

Python: `C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\python.exe` 3.14.0

`.env` / `backend/.env` were never opened. `GEMINI_API_KEY` was checked as a **name** only.

---

## 6.1 Part A — Block K test-client bug

### Mismatch

`backend/tests/test_block_k_signoff.py` tests are `async def` and call `await client.get(...)`.

`k_app` previously did:

```python
client = TestClient(fastapi_app)  # sync; .get() returns httpx/starlette Response
```

`await` on a `Response` is `TypeError: 'Response' object can't be awaited` (v2).

Installed versions: **httpx 0.28.1**, **fastapi 0.111.0**. `httpx.ASGITransport` exists. `AsyncClient.__init__` has `transport`, **not** `app=` (so the unused `k_app_async` path `AsyncClient(app=fastapi_app)` is not valid on this httpx).

### Fix (attempt 1 of 3 — succeeded)

`.bak`: `backend/tests/conftest.py.bak`

`k_app` is now a `pytest_asyncio` fixture that yields `httpx.AsyncClient(transport=ASGITransport(app=...), base_url="http://test")`. The test file was not restructured. `k_app_async` was left unused/unedited.

### Confirmation K1–K3 now **execute**

```
python -m pytest tests/test_block_k_signoff.py -v --tb=short -s
```

The await TypeError is **gone**. Every test reached the HTTP assertion:

```
test_k1_allow_then_deny_after_revoke FAILED
  AssertionError: {"error":{"code":"UnauthorizedError","message":"Invalid token: The specified alg value is not allowed",...}}
  assert 401 == 200

test_k1_missing_token_401 FAILED
  assert 403 == 401

test_k1_not_found_404 FAILED
  assert 401 == 404

test_k2_streams_large_document FAILED
  assert 401 == 200  (same "alg value is not allowed")

test_k2_small_document_not_streamed FAILED
  assert 401 == 200

test_k3_structure_fidelity FAILED
  assert 401 == 200

test_k3_redacts_hidden_fields_for_non_owner FAILED
  assert 401 == 200

====================== 7 failed, 187 warnings in 16.92s =======================
```

Cause of the new failures: `make_bearer()` in `backend/tests/conftest.py` encodes **HS256** (`jwt.encode(..., algorithm="HS256")`). `get_current_user` → `token_service.validate_token` rejects that alg (`The specified alg value is not allowed`; platform JWT is RS256). **Not fixed** — out of scope (harness JWT, not the test-client bug).

| ID | Architecture criterion | Result | Evidence |
|----|------------------------|--------|----------|
| K1 | ACL re-check, 100% post-revoke deny | **FAIL** | GET executed; 401 alg-not-allowed before any ACL revoke loop |
| K2 | Stream >10MB, bounded memory | **FAIL** | GET executed; 401 alg-not-allowed; streaming/memory never measured |
| K3 | Structure fidelity 100% | **FAIL** | GET executed; 401 alg-not-allowed |

**Phase:** Phase 1 (in-memory store + mock ACL). Phase 2 MinIO path still not exercised by this suite.

---

## 6.2 Part B — Gemini adapter, searched properly

The v2 Part C search used Anthropic/OpenAI/`LLM_PROVIDER`/`LlmProvider` and missed Gemini. This pass searched `backend/app/services/assistant/`, `assistant_orchestrator/`, `backend/app/core/config.py`, `backend/app/services/`, requirements, and pyproject for:

`gemini`, `Gemini`, `GEMINI`, `google.generativeai`, `google-generativeai`, `genai`, `vertexai`, `GoogleGenerativeAI`, `ChatGoogleGenerativeAI`, `GenerativeModel`, `generate_content`.

### What exists

| Location | Finding |
|----------|---------|
| `backend/requirements.txt` / `pyproject.toml` | `google-generativeai==0.8.3` / `^0.8.3` |
| `langchain-google-genai` / `ChatGoogleGenerativeAI` | **Not** a dependency |
| `backend/app/core/config.py` | `gemini_api_key: Optional[str] = Field(default=None)` (pydantic-settings maps env `GEMINI_API_KEY`). `llm_provider` aliases `LLM_PROVIDER` **and** `EMBEDDING_PROVIDER`. Property `embedding_provider` **returns `llm_provider`**. |
| `backend/app/services/embedding.py` | **`GeminiEmbeddingProvider`** — `google.generativeai` + `genai.embed_content` only. Switch: `provider_name == "gemini"` vs `"fake"`. |
| Assistant graph / `response_generator` | **No matches** for any Gemini/genai/vertex/ChatGoogle term |
| `generate_content` / `GenerativeModel` | **Only** `embed_content` in `embedding.py` |

### Key name vs process env (values never printed)

```
process_GEMINI_API_KEY=UNSET
gemini_api_key_present True
provider_is_fake True
provider_is_gemini False
anthropic_api_key_present False
```

Settings loaded `GEMINI_API_KEY` from the env file (name present, value not printed). Active provider is still **fake**, not `gemini`.

### Is there a real Gemini **chat** LLM adapter?

**No.** There is a real Gemini **embedding** adapter (`GeminiEmbeddingProvider`), used when `LLM_PROVIDER`/`EMBEDDING_PROVIDER` is `"gemini"`. It is **not** wired into Block L’s chat path. `response_generator` still templates search snippets. A configured `GEMINI_API_KEY` with no chat code path that reads it is exactly that: key present, chat unused.

`LLM_PROVIDER=gemini` would select Gemini **embeddings**, not a chat model. That is not architecture L4 (`LlmProvider` swap for the assistant).

**Do not wire it up** — reported only, per scope.

---

## 6.3 Part C — L1–L4

No wired Gemini (or other) chat adapter. Per the prompt: **do not run L1–L4 against nothing.**

| ID | Architecture criterion | Result | Reason |
|----|------------------------|--------|--------|
| L1 | ≥20 prompt-log red-team, 0 leaks into the prompt | **BLOCKED** | No chat prompt is assembled or sent to Gemini/`generate_content`. Running the file-named tenant-403 test would not test L1 |
| L2 | ≥30 answers, citations resolve via real K | **BLOCKED** | No LLM answers to sample; K1–K3 themselves FAIL (401). File-named L2 is NDJSON, not citation-via-K |
| L3 | Adversarial over-search, max tool-call rounds | **BLOCKED** | No such suite; graph is a fixed DAG. Not a Gemini-run failure |
| L4 | Swap `LlmProvider` via config | **BLOCKED** | No chat `LlmProvider`. Gemini package is embeddings-only |

**Cost check-in:** not applicable — no live chat calls were made. Estimated billed Gemini **chat** completions: **0**. Actual: **0**. (A Gemini **embedding** run was also not started; provider is fake.)

---

## 6.4 Part D — Block Q

Q PASS requires K1–K3 **and** L1–L4 all passing for real, with L2 as the K→L proof.

| Required | This session |
|----------|----------------|
| K1–K3 | **FAIL** (suite now runs; blocked on HS256 vs RS256 JWT, not the await bug) |
| L1–L4 | **BLOCKED** (no chat LLM adapter, Gemini or otherwise) |

**Q is not PASS.** Remaining blockers, named:

1. K signoff tokens: `make_bearer` HS256 vs `token_service` RS256 (`alg value is not allowed`).
2. L chat path: Gemini exists only as embeddings; `response_generator` is still a template; architecture L1/L4 are not testable until a chat adapter is scoped and wired.

The §24 tracking table’s “Q — Done (13/8/2026)” still does not match. Not edited here.

---

## 6.5 Updated overall D–L status

D–J rows are from prior passes, not re-run here.

| Block | Phase 1 (mock) | Phase 2 (real infra) | Notes |
|-------|----------------|----------------------|--------|
| D Storage | PASS (prior) | **PASS** (prior) | |
| E Chunking | PASS (prior) | **PASS** (prior) | |
| F Lexical | PASS (prior) | **PASS** (prior) | |
| G Vector | PASS (prior) | **PASS** (prior) | |
| H Graph | PASS (prior) | **PASS** (prior) | |
| I Signals | PASS (prior) | **PASS** (prior) | |
| J Federator | PASS (prior) | **PASS** (prior) | |
| K Reader | Suite **executes**; K1–K3 **FAIL** 401 alg | **Not reached** | Await bug fixed; JWT alg mismatch not fixed |
| L Orchestrator | Architecture L1–L4 **BLOCKED** | **Not reached** | Gemini = embeddings only; key name present, chat unused |
| Q (K+L integration) | **Not PASS** | **Not PASS** | Blockers: K JWT alg; L missing chat adapter |

**Bottom line:** K tests no longer die on `await`. They die on HS256 vs RS256. Broader Gemini search found `google-generativeai` + `GeminiEmbeddingProvider` + a present `GEMINI_API_KEY` **name** — not a chat adapter on the L response path. L1–L4 **BLOCKED**. Q is not done.

Stopped here. No Gemini wiring, no JWT helper change, no `SIGNOFF.md` edits, no commit, no M/N/O.
