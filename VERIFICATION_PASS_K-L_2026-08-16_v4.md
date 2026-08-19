# Independent Verification Pass v4 — Block K JWT alg + OpenRouter/Qwen re-check

**Date:** 2026-08-16  
**Type:** JWT harness already RS256 (re-verified) + OpenRouter/`QWEN_MODEL` diagnostic. No adapter wired.  
**This file is not `SIGNOFF.md`.** v3 stays as a record.

**Commit tested:** `5ce77b1a97f3bf0ea0ba980282940f517e7ad911` (`Add: Block N completed and tested`)  
**Branch:** `Pratham`  
**Repo:** `logicinnovationlabs/Sync-AI-Final`

Python: `C:\Users\Ishu Raj\AppData\Local\Python\pythoncore-3.14-64\python.exe` 3.14.0

`.env` / `backend/.env` were never opened. Names only: `OPENROUTER_API_KEY`, `QWEN_MODEL`, `GEMINI_API_KEY`.

---

## 6.1 Part A — JWT algorithm mismatch

### Which side was wrong

| Side | Algorithm / key |
|------|-----------------|
| Real issuer | `TokenService.issue_access_token` — `jwt.encode(..., algorithm=self.algorithm)` with `settings.jwt_algorithm` **RS256**, RSA PEM, `kid` header. Called from `auth.py` / `oauth_service.py`. |
| Real verifier | `get_current_user` → `validate_token` → `jwt.decode(..., algorithms=[self.algorithm], issuer=self.issuer)`. Same RS256. |
| Old test helper | HS256 HMAC (`JWT_SECRET_KEY` / `"test-secret-key"`). |

Issuer and verifier **agree**. The test double was the bug.

### Fix status

Already applied on disk from the previous session (no further edit this session). `make_bearer` now signs RS256 via `token_service._load_keys()` + `algorithm=token_service.algorithm`.

This session: `jwt_algorithm RS256`. Re-run:

```
python -m pytest tests/test_block_k_signoff.py -v --tb=line -s
```

**`401 Invalid token: The specified alg value is not allowed` is gone.** Failures are past auth:

```
test_k1_allow_then_deny_after_revoke FAILED
  {"detail":"Tenant resolution failed: badly formed hexadecimal UUID string"}
  assert 500 == 200

test_k1_missing_token_401 FAILED
  assert 403 == 401

test_k1_not_found_404 FAILED
  assert 500 == 404

test_k2_streams_large_document FAILED
  assert 500 == 200  (same UUID error)

test_k2_small_document_not_streamed FAILED
  assert 500 == 200

test_k3_structure_fidelity FAILED
  assert 500 == 200  (same UUID error)

test_k3_redacts_hidden_fields_for_non_owner FAILED
  assert 500 == 200

====================== 7 failed, 157 warnings in 17.62s =======================
```

`GET /api/v1/document/{id}` uses `Depends(get_tenant)` → `tenant_resolver.resolve` → `UUID(tenant_id)`. Suite constant is `"tenant-k"`. Not the JWT alg bug; not changed.

| ID | Architecture criterion | Result | Evidence |
|----|------------------------|--------|----------|
| K1 | ACL re-check, 100% post-revoke deny | **FAIL** | JWT accepted; 500 tenant UUID before revoke loop |
| K2 | Stream >10MB, bounded memory | **FAIL** | JWT accepted; 500 tenant UUID; stream never measured |
| K3 | Structure fidelity 100% | **FAIL** | JWT accepted; 500 tenant UUID |

**Phase:** Phase 1 (in-memory store + mock ACL).

---

## 6.2 Part B — OpenRouter / Qwen / Gemini, searched as specified

Prior passes searched Anthropic/OpenAI class names, then Gemini SDK names, then Qwen/DashScope names. They did **not** treat OpenRouter as the likely OpenAI-compatible `base_url` + `QWEN_MODEL` string-routing shape. This pass did.

### Config names (from code, not assumed)

```236:243:backend/app/core/config.py
    openrouter_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "openrouter_api_key"),
    )
    qwen_model: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("QWEN_MODEL", "qwen_model"),
    )
```

Comment on that block: `"LLM providers (optional until used)"`.

Name-only presence this session (values never printed):

```
openrouter_api_key_present True
qwen_model_present True
gemini_api_key_present True
provider_is_fake True
provider_is_gemini False
```

### Usage-site trace

| Search | Result |
|--------|--------|
| `OPENROUTER` / `openrouter` / `openrouter.ai` in `assistant/`, `assistant_orchestrator/`, `config.py` | **Config field only** (`openrouter_api_key`). Also listed in `backend/scripts/check_env_presence.py` and `backend/.env.example`. **Zero** construction sites. |
| `QWEN_MODEL` / `qwen_model` whole-repo `.py` | **Same:** `config.py` + `check_env_presence.py` only. Never passed as `model=` / `model_name=` to a client. |
| Every `openai.OpenAI` / `ChatOpenAI` / `AsyncOpenAI` | **None** in assistant or orchestrator. Only `AsyncAzureOpenAI` in `services/block-e-chunking/app/embeddings/azure_provider.py` (Block E embeddings, not L chat). |
| Every `base_url` / `api_base` in `backend/app` | Database URLs, webhook URLs, httpx to F/G/H/K/I. **No** `https://openrouter.ai/api/v1`. |
| `dashscope` / `ChatTongyi` / `Tongyi` | **No matches** |
| `openai` / `dashscope` / `langchain-openai` in `backend/requirements.txt` and `backend/pyproject.toml` | **Not pinned** |
| Assistant `httpx.AsyncClient` | `SearchToolbox` only — federator / graph / document / signals HTTP, not chat completions |

`LLM_PROVIDER` remains an **embedding** switch (`fake` / `gemini`) via `embedding_provider` property → `EmbeddingService`. No separate chat-provider switch.

### Three providers, one place

| Credential / name | Present in settings? | What the code does with it |
|-------------------|----------------------|----------------------------|
| `GEMINI_API_KEY` | Yes | **Embeddings only.** `GeminiEmbeddingProvider` → `genai.embed_content`. Re-confirmed; `LLM_PROVIDER` currently **fake**, so even embeddings are not using Gemini at runtime. |
| `OPENROUTER_API_KEY` | Yes | **Unused.** No OpenAI-compatible client, no `base_url` to OpenRouter. |
| `QWEN_MODEL` | Yes | **Unused.** Not embeddings, not chat. Not passed into any client. |

`response_generator` is still a snippet template (`backend/app/services/assistant/core/graph.py` ~345–378). It does not call OpenRouter, Qwen, or Gemini chat.

**There is no wired OpenRouter/Qwen chat adapter** (and no unused-but-constructed client sitting beside the template path). Two chat-related credentials + a model name exist in config with **no consumer**. Not wired this session.

---

## 6.3 Part C — L1–L4

No wired chat adapter. **Did not run L1–L4 against the template path.**

| ID | Architecture criterion | Result | Reason |
|----|------------------------|--------|--------|
| L1 | ≥20 prompt-log red-team | **BLOCKED** | No prompt is sent to OpenRouter/Qwen/Gemini chat |
| L2 | ≥30 answers via real K | **BLOCKED** | No LLM answers; K1–K3 FAIL (tenant UUID) |
| L3 | Max tool-call rounds | **BLOCKED** | No such suite; fixed DAG |
| L4 | Config-only `LlmProvider` swap | **BLOCKED** | No chat provider. `OPENROUTER_API_KEY` + `QWEN_MODEL` unread; `LLM_PROVIDER` is embeddings `fake`/`gemini` |

**Cost check-in:** not applicable. Estimated billed OpenRouter/Qwen chat completions: **0**. Actual: **0**.

---

## 6.4 Part D — Block Q

Q PASS = K1–K3 and L1–L4 all pass for real, with L2 proving K→L.

| Required | This session |
|----------|----------------|
| K1–K3 | **FAIL** (JWT alg fixed; 500 `badly formed hexadecimal UUID string` on `"tenant-k"`) |
| L1–L4 | **BLOCKED** (`OPENROUTER_API_KEY` + `QWEN_MODEL` present, unused; no chat client) |

**Q is not PASS.** Remaining blockers, named:

1. K: `get_tenant` / `UUID(tenant_id)` vs signoff suite `"tenant-k"`.
2. L: no chat adapter; OpenRouter key and Qwen model name are config-only.

§24 tracking table “Q — Done (13/8/2026)” still does not match. Not edited here.

---

## 6.5 Updated overall D–L status

D–J from prior passes, not re-run.

| Block | Phase 1 (mock) | Phase 2 (real infra) | Notes |
|-------|----------------|----------------------|--------|
| D Storage | PASS (prior) | **PASS** (prior) | |
| E Chunking | PASS (prior) | **PASS** (prior) | |
| F Lexical | PASS (prior) | **PASS** (prior) | |
| G Vector | PASS (prior) | **PASS** (prior) | |
| H Graph | PASS (prior) | **PASS** (prior) | |
| I Signals | PASS (prior) | **PASS** (prior) | |
| J Federator | PASS (prior) | **PASS** (prior) | |
| K Reader | Runs past JWT; K1–K3 **FAIL** 500 tenant UUID | **Not reached** | `make_bearer` RS256; `"tenant-k"` is not a UUID |
| L Orchestrator | Architecture L1–L4 **BLOCKED** | **Not reached** | OpenRouter + Qwen names present, unread; Gemini embeddings-only |
| Q (K+L integration) | **Not PASS** | **Not PASS** | Blockers: K tenant UUID; L missing chat wiring |

**Bottom line:** JWT alg is fixed and stayed fixed. OpenRouter is the exact env-var name `OPENROUTER_API_KEY`; together with `QWEN_MODEL` it is **not** wired to any `OpenAI`/`ChatOpenAI`/`base_url=openrouter.ai` client. Gemini remains embeddings-only. L1–L4 **BLOCKED**. Q is not done.

Stopped here. No OpenRouter wiring, no tenant-resolver change, no `SIGNOFF.md` edits, no commit, no M/N/O.
