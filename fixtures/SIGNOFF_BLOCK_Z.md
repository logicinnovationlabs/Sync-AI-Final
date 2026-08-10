# Block Z Signoff - Shared Fixtures & Contracts (Z1-Z3)

**Block:** Z - Reference fixtures, contract mocks, swap readiness  
**Architecture:** section 24  
**Engineer date:** 2026-08-08  
**Engineer:** Cursor Agent  
**Reviewer:** PENDING  
**Fixtures version:** v2.1  
**Status:** Provisional evidence only - **not** formal production signoff

---

## Scope

Shared package under fixtures/ used by the unified Block Z-O verification suite
(tests/test_block_z.py, contract mock server, fixture linter).

This report documents Z1-Z3 evidence against fixtures **v2** expanded to
architecture section 24 sizes. Independent human review is still required before any
formal production signoff claim.

---

## Section 24 target sizes (achieved)

| Artifact | Target | Achieved |
|----------|--------|----------|
| Documents | 60 | 60 |
| Principals | 25 | 25 |
| Multi-source identities (3+ systems) | 8 | 8 |
| ACL red-team cases | 15 | 15 |
| Labeled relevance queries (grades 0-3) | 30 | 30 |
| Groups | consistent | 10 |
| ACL matrix entries | consistent | generated from docs/groups |
| Graph edges | consistent | 111 |
| Activity events | consistent (optional) | 65 |

---

## Criteria

| ID | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| **Z1** | Contracts present and parseable; optional live mock sampling with response-shape checks | **PASS** | tests/test_block_z.py::test_z1_contracts_present_and_parseable - >=10 OpenAPI contracts under contracts/, 0 schema violations |
| **Z2** | Fixture lint + version alignment with MANIFEST | **PASS** | tests/helpers/fixture_linter.py -> documents=60 principals=25 groups=10 errors=0; all fixture files version=v2 matching FIXTURES_VERSION |
| **Z3** | Mock shape normalization / swap readiness | **PASS** | tests/test_block_z.py::test_z3_swap_shape_normalization - normalized lexical search shapes stable across variable fields |

---

## Commands run (2026-08-08)

```text
.venv\Scripts\python.exe fixtures\generate_fixtures.py
.venv\Scripts\python.exe -m tests.helpers.fixture_linter --fixtures fixtures
.venv\Scripts\python.exe -m pytest tests\test_block_z.py tests\test_blocks\test_block_z.py -v
.venv\Scripts\python.exe -m pytest tests\test_block_c.py tests\test_block_f.py tests\test_block_g.py tests\test_block_h.py tests\test_block_j.py -v
```

Results:

- Fixture linter: **errors=0**
- Block Z: **6 passed** (shim + direct)
- C/F/G/H/J provisional smoke: **19 passed, 1 skipped** (C integration skip)

---

## Package layout (fixtures/)

| File | Role |
|------|------|
| MANIFEST.json | version **v2**, counts, fixture list |
| documents.json | 60 docs (code/prose/tickets/emails/wiki; multi-source) |
| principals.json | 25 principals across tenant-a/b/c |
| groups.json | 10 groups with consistent membership |
| acl_matrix.json | OWNER/READ matrix derived from docs/groups |
| acl_redteam_cases.json | 15 cases (direct/group/inherited allow, deny, unshare, deleted, ...) |
| relevance_labels.json | 30 queries + flat labels[] graded 0-3 (NDCG-ready) |
| multi_source_identities.json | 8 principals with >=3 source systems |
| graph_edges.json | OWNS / REFERENCES / MEMBER_OF / WORKED_ON |
| activity_events.json | 65 events tied to shared docs/principals |
| performance_baselines.json | latency baselines for provisional tests |
| crawl_expectations.json | per-source expected counts + credential patterns |
| generate_fixtures.py | deterministic regenerator |

Legacy IDs preserved for provisional hardcodes: doc-roadmap, doc-api-docs,
doc-security, doc-onboarding, doc-restricted, principal-alice / bob /
carol / diana.

---

## Multi-source identity (8 x 3+ systems)

| Principal | Source systems |
|-----------|----------------|
| principal-alice | google_drive, google_gmail, github |
| principal-bob | google_drive, google_gmail, jira |
| principal-carol | google_drive, slack, confluence |
| principal-diana | google_gmail, github, notion |
| principal-erin | google_drive, google_gmail, slack |
| principal-frank | jira, confluence, github |
| principal-grace | google_drive, slack, jira |
| principal-hank | google_gmail, notion, confluence |

---

## Blocks still on private / local fixtures (note only)

These services still ship block-local fixtures (often tagged block-*-local).
Several already wire FIXTURES_PATH for a future cutover; no mass migration
performed in this change.

| Block | Local fixtures | FIXTURES_PATH wired? |
|-------|----------------|----------------------|
| F lexical | services/block-f-lexical-search/fixtures/ | service-local package |
| G vector | services/block-g-vector-search/fixtures/ | service pattern / local |
| H graph | services/block-h-graph/fixtures/ | yes |
| I signals | services/block-i-signals/fixtures/ | yes |
| J federator | services/block-j-query-federator/fixtures/ | yes |
| E chunking | local code/oversized fixtures | partial |
| C backend | backend / tests/fixtures/block_c/ extras | separate |

Unified suite (tests/) already defaults to repo-root fixtures/ (v2).

---

## Reviewer checklist (PENDING)

- [ ] Confirm section 24 counts and cross-references via fixture-linter
- [ ] Spot-check red-team expected outcomes vs ACL matrix
- [ ] Spot-check graded relevance set for NDCG use
- [ ] Decide cutover plan for block-local packages via FIXTURES_PATH
- [ ] Formal production signoff signature (not claimed here)

**Reviewer:** PENDING  
**Formal production signoff:** **NOT CLAIMED**

## Fixtures v2.1 — Code Corpus (2026-08-09)

Added shared `fixtures/code_corpus/` (36 files: python=19, javascript=11, go=6) migrated from Block E private fixtures (private copy retained). MANIFEST bumped to **v2.1**. Block E E1 prefers `FIXTURES_PATH/code_corpus` when set; falls back to private `services/block-e-chunking/fixtures/code`. E1 re-run this session: **PASS** (`services/block-e-chunking/evidence/e1_shared_code_corpus_full_20260809.txt`).

