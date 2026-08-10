# Full Signoff Suite Results — Blocks A–E
Date: 2026-08-05
HEAD: d391bb0 (Ishu)

| Block | Test ID | Result | Notes |
|-------|---------|--------|-------|
| A | A1 | PASS | Docker backend-test → block-a-verify-pg:5434 |
| A | A2 | PASS | |
| A | A3 | PASS | fixtures+scripts mounted |
| A | A4 | PASS | |
| A | A5 | PASS | |
| B | B1 | PASS | test_signoff_block_b.py (drive+gmail) |
| B | B2 | PASS | transform fallback when pipeline/magic unavailable |
| B | B3 | PASS | |
| B | B4 | PASS | |
| B | B5 | PASS | (+ B6/B7 also PASS) |
| C | C1 | PASS | Docker + libmagic + Block C pip deps |
| C | C2 | PASS | |
| C | C3 | PASS | |
| C | C4 | PASS | (+ C5–C9 also PASS; 10/10 in test_signoff_block_c.py) |
| D | D1 | PASS | test_D1_provisioning_time_local.py @ :5435 |
| D | D2 | PASS | after installing boto3 for MinIO checks |
| D | D3 | PASS | |
| D | D4 | PASS | |
| E | E1 | PASS | verify_component4_code_chunker.py — 36 files, 428 chunks |
| E | E2 | PASS | 548.9 docs/min agg; worst window 546.3 >= 400 |
| E | E3 | PASS | after clearing leftover embedding_jobs |
| E | E4 | PASS | UTF-8 console; deterministic chunk_id |

Overall: ALL PASS
