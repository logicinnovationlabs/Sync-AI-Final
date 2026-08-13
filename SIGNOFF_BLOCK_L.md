# SIGNOFF_BLOCK_L — Assistant Orchestrator

**Engineer:** Cursor Agent (Block L execution)  
**Reviewer:** PENDING (§24 independent human review not claimed)  
**Branch:** `block-l` (cut from clean `Ishu` at `6a145ec`)  
**Commit:** single Block L commit on `block-l` (signoff encoding fixed before merge)  
**Date:** 2026-08-11

---

## 1. Scope of what was built

New package `assistant_orchestrator/` (isolated namespace — no Block B–J remediation paths touched):

| Path | Role |
|------|------|
| `domain/models.py` | `OrchestratorRequest`, `ToolCall`, `ToolResult`, `SessionContext`, `BlobRef` |
| `infrastructure/tools.py` | `SearchToolbox` — httpx wrappers for Federator / KG / Document Reader / Signals |
| `infrastructure/memory_store.py` | Tenant-scoped episodic memory on Postgres `:5433` |
| `core/intent_router.py` | `search` / `read` / `chat` classification |
| `core/ranker_boost.py` | Additive Activity Signal boost on Ranking Service scores |
| `core/graph.py` | LangGraph: intent_router -> parallel_searcher -> personalized_ranker -> response_generator -> END |
| `api/routes.py` | `POST /orchestrator/chat` (NDJSON stream), session GET, RS256 JWT auth pattern |
| `tests/verify_block_l_*.py` | Five evidence scripts |
| `SIGNOFF_BLOCK_L.md` | This document |

Design rules implemented:
1. **ACL pass-through** — opaque `acl_compiled_filter: bytes` forwarded unmodified; no control-flow branching on ACL contents.
2. **Signal-aware ranking** — Federator base scores preserved; boost applied only to `boosted_score`.
3. **Search vs Read switch** — confidence `< 0.6` triggers Document Reader fallback.
4. **Multi-tenant isolation** — session/memory PK includes `tenant_id`; cross-tenant loads return empty/isolated rows.

---

## 2. Scope Boundary decision

- Started on clean `Ishu` (`nothing to commit, working tree clean`).
- Created dedicated `block-l` branch so Block E remediation (E3 duplicate-enqueue) cannot collide.
- **Deliberately not touched:** `backend/app/workers/tasks.py`, Block E chunking/embedding workers, Blocks F–J source trees, shared Celery config.
- No pre-existing `assistant_orchestrator/` package; provisional `tests/test_blocks/test_block_l.py` left unchanged.

---

## 3. Documented deviations from Master Prompt

| Spec assumption | Repo reality | Handling |
|-----------------|--------------|----------|
| Opaque ACL bytes from Identity Resolver | JWT surface emits `List[str]` acl_terms | Terms wrapped as UTF-8 JSON bytes; Block L never branches on contents. Wire proof via identical `X-ACL-Compiled-Filter` hex. |
| Separate Ranking Service HTTP API | Ranking is in-process inside Block J Federator | L consumes Federator `results[].score` as base Ranking output, then applies signal boost. |
| Importable clients for J/H/K/I | HTTP APIs exist; no reusable client packages | `SearchToolbox` implements thin httpx wrappers (not silent stubs of L behavior). |
| Full Block J/H/K/I containers for every verify | J/I port collision (both default 8089); H/K/I apps not all up | Verification uses contract-compatible local stub backends on dedicated ports plus real Postgres `:5433` and real Qdrant `:6333`. |
| LangGraph already in repo | Not present | Added `langgraph` dependency for Block L only. |
| Response LLM streaming | No production LLM wired for L in this pass | Deterministic synthesizer streams NDJSON tokens; activity ingest is async/non-blocking. |

---

## 4. Docker / infra health

| Service | Check | Result |
|---------|-------|--------|
| Postgres `:5433` (`block_e_postgres`) | `pg_isready` | accepting connections (`postgres`/`verify`/`block_e`) |
| Redis Celery broker | `redis-cli ping` | `PONG`; Celery worker connected and ready |
| Qdrant `:6333` | `/healthz` + `/readyz` | 200 / `all shards are ready` (started via block-g compose; was down initially) |
| MinIO `:9000` / `:19000` | `/minio/health/ready` | 200 |
| OpenSearch `:9200` | `/_cluster/health` | green |
| Vault `:8200` | `/v1/sys/health` | 200 |
| Redpanda `:9644` | `/v1/status/ready` | ready |

Root has no single `docker-compose.yml`; used `docker-compose.deps.yml` + block-g Qdrant + already-running Block E/D/K infra.

---

## 5. Verification evidence

Commands (PowerShell):

```powershell
cd "D:\PROJECTS\Sync Ai Final"
$env:PYTHONPATH = (Get-Location).Path
$env:ORCHESTRATOR_DATABASE_URL = "postgresql://postgres:verify@127.0.0.1:5433/block_e"
& .\.venv\Scripts\python.exe assistant_orchestrator\tests\verify_block_l_acl_passthrough.py
& .\.venv\Scripts\python.exe assistant_orchestrator\tests\verify_block_l_signal_boost.py
& .\.venv\Scripts\python.exe assistant_orchestrator\tests\verify_block_l_search_vs_read_switch.py
& .\.venv\Scripts\python.exe assistant_orchestrator\tests\verify_block_l_multitenant_isolation.py
& .\.venv\Scripts\python.exe assistant_orchestrator\tests\verify_block_l_e2e_conversation.py
```

Full console capture: `assistant_orchestrator/tests/evidence_block_l_final.txt`

| Script | Result | Notes |
|--------|--------|-------|
| `verify_block_l_acl_passthrough.py` | **PASS** | 5/5 tools; wire hex identical to input ACL bytes |
| `verify_block_l_signal_boost.py` | **PASS** | doc-beta rank 1->0; base scores unchanged; boosted_score increased |
| `verify_block_l_search_vs_read_switch.py` | **PASS** | lowconf base 0.25 -> reader; highconf 0.92 -> no reader |
| `verify_block_l_multitenant_isolation.py` | **PASS** | Same session_id isolated by tenant; memory no cross-leak |
| `verify_block_l_e2e_conversation.py` | **PASS** | 3-turn stream; history=6; intents persisted; Qdrant readyz 200; latency n=3 |

---

## 6. Open risks / hardening gaps

- Downstream stub backends used for J/H/K/I HTTP during verify — wire Block L env URLs to live services before Integration signoff.
- Federator `SearchRequest` may reject unknown `acl_terms` / `orchestrator_mode` body fields when pointed at real Block J — may need header-only ACL pass-through adapter.
- Activity ingest is best-effort daemon thread; failures are logged, not retried.
- JWT unverified-decode fallback remains for empty `JWT_PUBLIC_KEY_PATH` (same pattern as other blocks test paths).
- No RLS on `orchestrator_sessions` / `orchestrator_memory` tables — isolation is application-level (analogous to earlier RLS-off findings).
- Response generator is deterministic, not a production LLM.

---

## 7. Explicit note

This document prepares evidence for section 24 signoff. It is **not** itself the independent human signoff.
