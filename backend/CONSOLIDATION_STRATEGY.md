# Block D-J Consolidation Strategy

## Overview
This document outlines the systematic consolidation of Blocks D-J from `services/` into the unified `backend/` structure.

## Consolidation Principles

1. **Preserve Working Logic**: Business logic stays identical - only imports change
2. **Eliminate Duplication**: Use shared `core/` modules for auth, config, ACL
3. **Modular Structure**: Each block becomes a clean module within backend
4. **Test Preservation**: All signoff tests must pass after consolidation

## File Movement Plan

### Block D: Storage & Encryption (Infrastructure)
```
services/block-d-storage/encryption/ → backend/app/storage/encryption/
services/block-d-storage/vault_client/ → backend/app/storage/vault/ (merge with existing)
services/block-d-storage/object_store_client/ → backend/app/storage/object_store.py
services/block-d-storage/backup_cli/ → backend/app/scripts/ (backup.py, restore.py)
services/block-d-storage/provisioning/ → backend/app/services/provisioning.py
services/block-d-storage/tests/ → backend/tests/test_block_d.py
```

### Block E: Chunking & Embeddings
```
services/block-e-chunking/app/services/chunkers/ → backend/app/services/chunking/
services/block-e-chunking/app/api/v1/embed.py → backend/app/api/v1/embed.py
services/block-e-chunking/app/models/ → backend/app/models/chunk.py
services/block-e-chunking/tests/ → backend/tests/test_block_e.py
DELETE: app/config.py, app/auth/jwt_auth.py
```

### Block F: Lexical Search
```
services/block-f-lexical-search/app/services/ → backend/app/services/lexical/
services/block-f-lexical-search/app/api/v1/ → backend/app/api/v1/search/lexical.py
services/block-f-lexical-search/tests/ → backend/tests/test_block_f.py
DELETE: app/config.py, app/auth/jwt_auth.py, app/services/acl_filter.py
```

### Block G: Vector Search
```
services/block-g-vector-search/app/services/ → backend/app/services/vector/
services/block-g-vector-search/app/api/v1/ → backend/app/api/v1/search/vector.py
services/block-g-vector-search/tests/ → backend/tests/test_block_g.py
DELETE: app/config.py, app/auth/jwt_auth.py, app/services/acl_filter.py
```

### Block H: Knowledge Graph
```
services/block-h-graph/app/services/ → backend/app/services/graph/
services/block-h-graph/app/api/v1/ → backend/app/api/v1/search/graph.py
services/block-h-graph/tests/ → backend/tests/test_block_h.py
DELETE: app/config.py, app/auth/jwt_auth.py
```

### Block I: Activity Signals
```
services/block-i-signals/app/services/ → backend/app/services/signals/
services/block-i-signals/app/api/v1/ → backend/app/api/v1/signals.py
services/block-i-signals/app/models/ → backend/app/models/signals.py
services/block-i-signals/tests/ → backend/tests/test_block_i.py
DELETE: app/config.py, app/auth/jwt_auth.py
```

### Block J: Query Federator
```
services/block-j-query-federator/app/services/ → backend/app/services/federator/
services/block-j-query-federator/app/api/v1/ → backend/app/api/v1/search/federated.py
services/block-j-query-federator/app/models.py → backend/app/models/search.py
services/block-j-query-federator/tests/ → backend/tests/test_block_j.py
DELETE: app/config.py, app/auth/jwt_auth.py, app/clients/
```

## Import Transformation Rules

### Old → New Import Patterns

| Old Import | New Import |
|-----------|------------|
| `from app.config import settings` | `from app.core.config import settings` |
| `from app.auth.jwt_auth import get_current_user` | `from app.api.deps import get_current_user` |
| `from app.services.acl_filter import apply_acl` | `from app.core.acl.filter import apply_acl` |
| `from app.models.X import Y` | `from app.models.X import Y` (stays same, just move files) |

## Shared Module Usage

All blocks will use:
- **Auth**: `backend/app/api/deps.py` (get_current_user, require_scope)
- **Config**: `backend/app/core/config.py` (settings singleton)
- **ACL**: `backend/app/core/acl/filter.py` (apply_acl, filter_by_permissions)
- **Exceptions**: `backend/app/core/exceptions.py`
- **Error Models**: `backend/app/core/errors.py`

## Signoff Tests to Preserve

All signoff tests MUST pass after consolidation:
- **D1-D4**: Storage provisioning, backup/restore, isolation, key rotation
- **E1-E4**: Chunking integrity, throughput, re-embed, idempotency
- **F1-F4**: Query latency, ACL enforcement, index lag, facet accuracy
- **G1-G4**: Recall, ACL prefilter, query latency, model versioning
- **H1-H3**: Edge fidelity, traversal latency, merge/split integrity
- **I1-I3**: Privacy threshold, retention enforcement, signal freshness
- **J1-J4**: End-to-end latency, zero-leak, ranking quality, graceful degradation

## Consolidation Phases

### Phase 1: Infrastructure (Block D)
Move storage utilities, encryption, backup scripts. No API routes to mount.

### Phase 2: Models
Move all models to `backend/app/models/` before moving services that depend on them.

### Phase 3: Services & APIs (Blocks E-J)
Move each block's services and API routes, updating imports as we go.

### Phase 4: Testing
Move all tests, adapt imports, verify all signoff criteria pass.

### Phase 5: Integration
Update main.py, docker-compose, requirements, migrations.

## Execution Order

1. Create new directory structure
2. Move Block D (storage infrastructure)
3. Move models (chunk.py, signals.py, search.py)
4. Move Block E (chunking) - pilot to verify pattern
5. Move Blocks F, G (search services)
6. Move Block H (graph)
7. Move Block I (signals)
8. Move Block J (federator)
9. Update main.py with all routers
10. Update config.py with all env vars
11. Update workers/tasks.py with new Celery tasks
12. Move all tests
13. Merge requirements.txt
14. Create new migrations
15. Update docker-compose.yml
16. Run full test suite

## Success Criteria

- [ ] All files moved from `services/` to `backend/app/`
- [ ] All duplicate config/auth files deleted
- [ ] All imports updated to use shared core
- [ ] All routers mounted in main.py
- [ ] All tests passing (A1-A7, B1-B7, C1-C9, D1-D4, E1-E4, F1-F4, G1-G4, H1-H3, I1-I3, J1-J4)
- [ ] Docker Compose working with all services
- [ ] Requirements merged and deduplicated
