# Independent Reviewer Packet Index (Blocks Z–J)

> **§24.1:** All blocks require an **independent human reviewer**. Engineer self-reports are **not** signoffs. Every reviewer field is **PENDING**.

Shared fixtures: **`fixtures_version` = v2** (`fixtures/MANIFEST.json` — includes `code_corpus/` directory).

---

## Build / Dependency Order

```
Z → A → B/D (parallel) → C → E/F (parallel) → G/H/I (parallel) → J
```

| Order | Block | Packet path |
|-------|-------|-------------|
| 1 | **Z** — Shared Fixtures | [`fixtures/REVIEWER_PACKET.md`](fixtures/REVIEWER_PACKET.md) |
| 2 | **A** — Tenancy / Auth | [`backend/REVIEWER_PACKET_BLOCK_A.md`](backend/REVIEWER_PACKET_BLOCK_A.md) |
| 3a | **B** — Connectors | [`backend/REVIEWER_PACKET_BLOCK_B.md`](backend/REVIEWER_PACKET_BLOCK_B.md) |
| 3b | **D** — Storage | [`services/block-d-storage/REVIEWER_PACKET.md`](services/block-d-storage/REVIEWER_PACKET.md) |
| 4 | **C** — Normalization / ACL | [`backend/REVIEWER_PACKET_BLOCK_C.md`](backend/REVIEWER_PACKET_BLOCK_C.md) |
| 5a | **E** — Chunking / Embedding | [`services/block-e-chunking/REVIEWER_PACKET.md`](services/block-e-chunking/REVIEWER_PACKET.md) |
| 5b | **F** — Lexical Search | [`services/block-f-lexical-search/REVIEWER_PACKET.md`](services/block-f-lexical-search/REVIEWER_PACKET.md) |
| 6a | **G** — Vector Search | [`services/block-g-vector-search/REVIEWER_PACKET.md`](services/block-g-vector-search/REVIEWER_PACKET.md) |
| 6b | **H** — Knowledge Graph | [`services/block-h-graph/REVIEWER_PACKET.md`](services/block-h-graph/REVIEWER_PACKET.md) |
| 6c | **I** — Signals | [`services/block-i-signals/REVIEWER_PACKET.md`](services/block-i-signals/REVIEWER_PACKET.md) |
| 7 | **J** — Query Federator | [`services/block-j-query-federator/REVIEWER_PACKET.md`](services/block-j-query-federator/REVIEWER_PACKET.md) |

---

## Self-Reported Status Summary (engineer — not reviewer signoff)

| Block | Criteria | Engineer self-report | Reviewer | Blocking notes |
|-------|----------|---------------------|----------|----------------|
| **Z** | Z1–Z3 | PASS (provisional) | **PENDING** | Formal production signoff not claimed |
| **A** | A1–A5 | PASS | **PENDING** | Uses `block-a-verify-pg` :5434 |
| **B** | B1–B5 | **PARTIAL** | **PENDING** | B5 Phase 1+2 PASS; full B1–B7 Drive+Gmail still open; token renew ~2026-08-16 |
| **C** | C1–C4 | PASS | **PENDING** | |
| **D** | D1–D4 | PASS | **PENDING** | pgcrypto interim vs KMS |
| **E** | E1–E6 | PASS | **PENDING** | E2 Gemini interim; E1 uses shared `code_corpus/` |
| **F** | F1–F4 | PASS | **PENDING** | Block-local fixtures |
| **G** | G1–G4 | **PASS** (Gemini 768) | **PENDING** | G2 fixed 2026-08-09 evening |
| **H** | H1–H3 | PASS | **PENDING** | |
| **I** | I1–I3 | PASS | **PENDING** | |
| **J** | J1–J4 | Phase 1 PASS; Phase 2 **FAIL (J1)** | **PENDING** | Phase 2 p95 ~1379 ms > 800 |

---

## Cross-Cutting Reviewer Actions

1. Never print secrets from `backend/.env` — use placeholders (`<GEMINI_API_KEY>`, etc.).
2. Re-run each packet reproduce commands; fill PASS/FAIL tables in the packet file.
3. Do not rubber-stamp engineer self-reports as §24.1 signoff.

**All reviewers: PENDING**

---

## Status snapshot — amended 2026-08-10

Self-reported engineer status only. **Reviewer column remains PENDING for all blocks.**

| Block | Engineer status note |
|-------|----------------------|
| Z | PASS Z1–Z3; fixtures **v2** (+ code_corpus) |
| A, C, D, F, H, I | Prior Phase 1/2 PASS evidence stands |
| E | E1–E6 PASS; Gemini path |
| G | Gemini 768: G1–G4 **PASS** after G2 ACL/fixture fix |
| B | B5 Phase 2 real Gmail **PASS** (re-verified 2026-08-10); token renew ~2026-08-16 |
| J | Phase 2 **FAIL (J1 latency)**; J2–J4 PASS on real F/G/H |
