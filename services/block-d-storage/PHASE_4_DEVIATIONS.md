# Phase 4: Deviation and Decision Log

## Encryption Mechanism Resolution

**Finding:** pgcrypto is the actual, current implementation (not pgsodium)

**Evidence:**
- `EncryptionClient` uses pgcrypto functions (pgp_sym_encrypt/pgp_sym_decrypt)
- Code comments explicitly state: "This implementation uses pgcrypto, which is universally available and does not require special role permissions like pgsodium"
- Commit history confirms: "Refactor EncryptionClient to use pgcrypto-based encryption"
- Git log shows: "119200c Refactor EncryptionClient to use pgcrypto-based encryption and add verification scripts"

**Decision:** pgcrypto was intentionally chosen over pgsodium because:
- pgcrypto is universally available in Postgres without special role permissions
- pgcrypto does not require complex role grants like pgsodium
- The application manages keys directly via vault (passphrases stored as JSON envelopes)
- This aligns with architecture doc §15.2 / §9.1 requirements

**Obsolete Artifacts:**
The following files are obsolete pgsodium-related scripts from earlier work:
- `enable_vault_extension.py` - attempted to enable Supabase's vault extension (wraps pgsodium)
- `grant_pgsodium_permissions.py` - attempted to grant pgsodium-specific role permissions
- `verify_pgsodium_functions.py` - attempted to verify pgsodium functions
- These are artifacts from pre-refactor work and should be removed or archived

## Schema Verification Results

**Finding:** Tenant metadata table complies with vault-key-reference-only requirement

**Evidence:**
- `tenants.secrets_key_ref` column stores VARCHAR(255) key references
- Column comment: "Reference to vault key, not the secret itself. Resolved through VaultClient."
- No columns store raw credentials (password, secret, connection_string)
- Architecture compliance confirmed per §9.1/§28.2 requirements

**Decision:** No deviation - schema complies with architectural requirements

## Test Implementation Improvements

### D2 Backup/Restore Implementation Deviation

**Previous State:** 
- SIGNOFF.md noted: "Full pg_dump/pg_restore integration required for complete Phase 2 signoff (current implementation uses stub restore)"

**Current Implementation:**
- Enhanced `_dump_schema()` to dump actual table data as JSON with ordering
- Enhanced `_restore_schema()` to recreate tables and insert data from JSON
- Added proper checksum normalization for consistent verification
- Added in-memory storage for backup data during testing
- Unified closeout: `test_D2_backup_restore_local.py` also seeds 10 MinIO objects under the tenant prefix, deletes them, restores them, and asserts object count + SHA256 match

**Deviation:** 
- Schema dump still uses in-memory `_backup_data_store` (not yet writing dump blobs into MinIO via the CLI)
- Object integrity is verified against real MinIO in the D2 test; CLI wiring of object dumps into MinIO remains deferred

**Decision:** Documented deviation - row integrity via backup CLI; object integrity via MinIO in the D2 test harness

### D3 Storage-Layer Tenant Isolation Improvement

**Previous State:**
- SIGNOFF.md noted: "Real Postgres schema-permission test (test_D3_storage_isolation_real_postgres.py) skipped due to Docker unavailability on Windows, but mock-based path isolation verified"
- This was a FALSE PASS since it only tested path construction, not actual database permissions

**Current Implementation:**
- Created `test_D3_storage_isolation_local.py` using the existing local Postgres container
- Test creates real Postgres schemas (tenant_a, tenant_b) with separate users (user_a, user_b)
- Grants schema-level permissions and attempts 20 cross-tenant reads
- All 20 attempts correctly blocked at Postgres permission level (InsufficientPrivilege)
- Evidence provided for each rejection point showing database-level blocking

**Decision:** Resolved previous false PASS - now provides genuine storage-layer isolation verification

### D4 Key Rotation Test Enhancement

**Previous State:**
- Existing test had real Supabase connection but may not have had proper concurrent load testing

**Current Implementation:**
- Created `test_D4_key_rotation_local.py` with local Postgres container
- Implemented true concurrent load testing with ThreadPoolExecutor (10 workers, 70/30 read/write mix)
- Metrics tracking for total requests, failures during rotation, latency
- Verification of pre-rotation data decryption post-rotation
- Results: 9,101 total requests, 0 failures, 0 failed during rotation, all pre-rotation data decrypts correctly

**Decision:** Enhanced D4 test provides genuine zero-downtime rotation verification under load

## Environment Setup

**Local Testing Infrastructure:**
- Postgres container: `block-d-verify-pg` (postgres:16, port 5435)
- pgcrypto extension: Enabled and verified (v1.3)
- MinIO container: `block-d-verify-minio` (ports 9000/9001) for object storage testing
- These containers provide real dependencies for Phase 2 verification

**Decision:** Local containers provide sufficient real-environment testing without requiring external cloud services

## Summary of Deviations

1. **Encryption Mechanism:** pgcrypto (confirmed correct) - no deviation
2. **Schema Compliance:** Vault key references only (confirmed correct) - no deviation  
3. **Backup/Restore Storage:** In-memory vs object storage - documented deviation acceptable for verification
4. **D3 Isolation:** Resolved previous false PASS with real Postgres permission testing
5. **D4 Load Testing:** Enhanced with proper concurrent load generation and metrics

## Conclusion

All D1-D4 criteria now have genuine evidence from real local Postgres testing:
- D1: 10 tenants provisioned in 0.11s (well under 300s threshold)
- D2: Row counts and checksums match exactly (100 rows, same checksum)
- D3: 20/20 cross-tenant reads blocked at Postgres permission level
- D4: 9,101 requests under load, 0 failures during rotation, all pre-rotation data decrypts

The pgcrypto vs pgsodium discrepancy is resolved (pgcrypto is correct and intentional).
The tenant metadata table complies with vault-key-reference-only requirements.
Previous false PASS in D3 is corrected with real permission testing.