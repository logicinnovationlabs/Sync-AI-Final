# Refactoring Plan: Achieve 4-5 File Changes Per Connector

## Goal
Reduce new connector development to require changes in only 4-5 files (3 necessary + 1-2 optional).

## Current Issues

### Issue 1: Hardcoded `GOOGLE_SOURCES` List
**Location:** `backend/app/connectors/router.py` (line 52)

**Problem:**
```python
GOOGLE_SOURCES = ("google_drive", "google_gmail")

# Used in multiple functions:
for source_type in GOOGLE_SOURCES:
    # Organization connector setup
```

**Solution:**
```python
def get_provider_sources(provider_id: str) -> Tuple[str, ...]:
    """Get all source types for a provider from registry."""
    from app.connectors import provider_registry
    plugin = provider_registry.get(provider_id)
    return plugin.sources if plugin else ()

# Usage:
for source_type in get_provider_sources("google"):
    # Organization connector setup
```

**Files to Change:**
- `backend/app/connectors/router.py`

---

### Issue 2: Source-Type String Matching
**Location:** `backend/app/workers/tasks.py`, `backend/app/connectors/google/plugin.py`

**Problem:**
```python
if source_type.startswith("google_"):
    # Google-specific logic
elif source_type in ("onedrive", "outlook"):
    # Microsoft-specific logic
```

**Solution:**
```python
plugin = provider_registry.get_by_source(source_type)
if not plugin:
    raise ValueError(f"Unknown source_type: {source_type}")

# Use plugin methods for provider-specific behavior
auth = plugin.prepare_backfill(tenant_id, source_type, principal_id)
```

**Files to Change:**
- `backend/app/workers/tasks.py` (lines ~415-445)
- Any other files with source_type string matching

---

### Issue 3: Manual Frontend Type Updates
**Location:** `frontend/lib/api/connectors.ts`

**Problem:**
```typescript
export type BackendSourceType =
  | "google_drive"
  | "google_gmail"
  | "onedrive"
  | "outlook"
  // Must manually add each new connector
```

**Solution:** Auto-generate from backend

**Create:** `backend/scripts/generate_types.py`
```python
#!/usr/bin/env python3
"""Generate frontend types from backend connector registry."""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.connectors import provider_registry

def generate_connector_types():
    """Generate TypeScript types for connectors."""
    plugins = provider_registry.all_plugins()
    sources = []
    
    for plugin in plugins:
        sources.extend(plugin.sources)
    
    sources = sorted(set(sources))
    
    # Generate TypeScript union type
    ts_sources = "\n  | ".join(f'"{s}"' for s in sources)
    
    ts_content = f'''/**
 * Auto-generated from backend connector registry.
 * DO NOT EDIT MANUALLY - Run: python backend/scripts/generate_types.py
 */

export type BackendSourceType =
  | {ts_sources}
'''
    
    # Write to frontend file
    output_path = Path(__file__).parent.parent.parent / "frontend" / "lib" / "api" / "connector-types.ts"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(ts_content)
    
    print(f"✅ Generated {len(sources)} connector types: {', '.join(sources)}")
    print(f"📝 Written to: {output_path}")

if __name__ == "__main__":
    generate_connector_types()
```

**Update:** `frontend/lib/api/connectors.ts`
```typescript
// Import auto-generated types
import { BackendSourceType } from './connector-types'

// Export for backward compatibility
export type { BackendSourceType }
```

**Files to Create:**
- `backend/scripts/generate_types.py`
- `frontend/lib/api/connector-types.ts` (auto-generated)

**Files to Modify:**
- `frontend/lib/api/connectors.ts` (import instead of define)

---

## Refactoring Steps

### Step 1: Create Helper Functions (30 mins)

**File:** `backend/app/connectors/helpers.py` (NEW)

```python
"""Helper functions for connector operations."""

from typing import Tuple
from app.connectors import provider_registry


def get_provider_sources(provider_id: str) -> Tuple[str, ...]:
    """
    Get all source types for a provider.
    
    Example:
        >>> get_provider_sources("google")
        ("google_drive", "google_gmail")
        
        >>> get_provider_sources("microsoft")
        ("onedrive", "outlook")
    """
    plugin = provider_registry.get(provider_id)
    return plugin.sources if plugin else ()


def get_source_provider_id(source_type: str) -> str:
    """
    Get provider ID for a source type.
    
    Example:
        >>> get_source_provider_id("google_drive")
        "google"
        
        >>> get_source_provider_id("onedrive")
        "microsoft"
    """
    plugin = provider_registry.get_by_source(source_type)
    return plugin.provider_id if plugin else ""


def is_source_from_provider(source_type: str, provider_id: str) -> bool:
    """
    Check if a source belongs to a provider.
    
    Example:
        >>> is_source_from_provider("google_drive", "google")
        True
        
        >>> is_source_from_provider("onedrive", "google")
        False
    """
    return get_source_provider_id(source_type) == provider_id
```

### Step 2: Replace GOOGLE_SOURCES Usage (1 hour)

**File:** `backend/app/connectors/router.py`

```python
# BEFORE:
GOOGLE_SOURCES = ("google_drive", "google_gmail")

for source_type in GOOGLE_SOURCES:
    status_store.clear_status(
        tenant_id, source_type, user_id="organization"
    )

# AFTER:
from app.connectors.helpers import get_provider_sources

for source_type in get_provider_sources("google"):
    status_store.clear_status(
        tenant_id, source_type, user_id="organization"
    )
```

**Search & Replace:**
1. Find all `GOOGLE_SOURCES` usages
2. Replace with `get_provider_sources("google")`
3. Remove `GOOGLE_SOURCES` constant
4. Add import: `from app.connectors.helpers import get_provider_sources`

**Files to Update:**
- `backend/app/connectors/router.py` (~10 locations)

### Step 3: Remove Source Type String Matching (2 hours)

**File:** `backend/app/workers/tasks.py` (lines ~415-445)

```python
# BEFORE:
if source_type.startswith("google_"):
    from app.connectors.google.oauth import GoogleOAuthManager
    from app.connectors.google.token_store import PersistentGoogleTokenStore
    from app.connectors.google.keys import cursor_scope_id, google_oauth_token_key
    
    token_store = PersistentGoogleTokenStore(tenant_id)
    oauth_manager = GoogleOAuthManager(...)
    # ... more setup
    
elif source_type in ("onedrive", "outlook"):
    from app.connectors import provider_registry
    
    plugin = provider_registry.get_by_source(source_type)
    if not plugin or not plugin.prepare_backfill:
        raise ValueError(f"No provider plugin for source_type={source_type}")
    auth = plugin.prepare_backfill(tenant_id, source_type, principal_id)
    # ... use auth

# AFTER:
from app.connectors import provider_registry

plugin = provider_registry.get_by_source(source_type)
if not plugin or not plugin.prepare_backfill:
    raise ValueError(f"No provider plugin for source_type={source_type}")

auth = plugin.prepare_backfill(tenant_id, source_type, principal_id)
token_store = auth.token_store
oauth_manager = auth.oauth_manager
principal_id = auth.principal_id or principal_id
mailbox_email = auth.mailbox_email or ""

# Unified handling - no more if/elif
```

**Update Google Plugin** to match Microsoft pattern:

**File:** `backend/app/connectors/google/plugin.py`

```python
def prepare_backfill(
    tenant_id: str, source_type: str, principal_id: str = ""
) -> BackfillAuth:
    """Prepare auth objects for backfill - matches Microsoft pattern."""
    from app.connectors.google.oauth import GoogleOAuthManager
    from app.connectors.google.token_store import PersistentGoogleTokenStore
    from app.core.config import settings
    
    token_store = PersistentGoogleTokenStore(tenant_id)
    oauth_manager = GoogleOAuthManager(
        client_id=settings.google_client_id or "",
        client_secret=settings.google_client_secret or "",
        token_store=token_store,
    )
    
    # Lookup mailbox email from token
    mailbox_email = ""
    try:
        from app.connectors.google.keys import google_oauth_token_key
        data = token_store.get_token(google_oauth_token_key(tenant_id, principal_id, "personal")) or {}
        mailbox_email = str(data.get("mailbox_email") or "")
    except Exception:
        pass
    
    return BackfillAuth(
        token_store=token_store,
        oauth_manager=oauth_manager,
        principal_id=principal_id,
        mailbox_email=mailbox_email,
        client_id=settings.google_client_id or "",
        client_secret=settings.google_client_secret or "",
        allow_env_seed=True,  # Google supports env var seeding
    )
```

**Files to Update:**
- `backend/app/workers/tasks.py` (backfill_source function)
- `backend/app/connectors/google/plugin.py` (add/update prepare_backfill)

### Step 4: Auto-Generate Frontend Types (1 hour)

1. Create `backend/scripts/generate_types.py` (see code above)
2. Run script: `python backend/scripts/generate_types.py`
3. Update `frontend/lib/api/connectors.ts` to import from generated file
4. Add to package.json scripts:
   ```json
   "scripts": {
     "generate-types": "python ../backend/scripts/generate_types.py",
     "predev": "npm run generate-types",
     "prebuild": "npm run generate-types"
   }
   ```

**Files to Create:**
- `backend/scripts/generate_types.py`

**Files to Update:**
- `frontend/lib/api/connectors.ts`
- `frontend/package.json`

---

## Testing Plan

### Test 1: Existing Connectors Still Work
```bash
# Test each connector's status endpoint
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/connectors/google_drive/status"

curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/connectors/onedrive/status"
```

### Test 2: Backfill Uses Unified Path
```bash
# Trigger backfill for Google Drive
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/connectors/google_drive/backfill"

# Trigger backfill for OneDrive
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/connectors/onedrive/backfill"

# Check logs - should NOT see "if source_type.startswith" branches
tail -f celery-worker.log | grep "Backfill"
```

### Test 3: Frontend Types Generated
```bash
# Run generation
python backend/scripts/generate_types.py

# Verify output
cat frontend/lib/api/connector-types.ts

# Expected:
# export type BackendSourceType =
#   | "google_drive"
#   | "google_gmail"
#   | "onedrive"
#   | "outlook"
```

### Test 4: Organization Connectors
```bash
# Google organization connector should still work
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/connectors/admin/google/organization/google_drive/backfill"
```

---

## Rollout Strategy

### Phase 1: Safe Changes (Low Risk)
1. ✅ Create helper functions (`helpers.py`)
2. ✅ Add tests for helpers
3. ✅ Create frontend type generator script

**Risk:** None - additive only

### Phase 2: Replace Hardcoded Lists (Medium Risk)
1. ✅ Replace `GOOGLE_SOURCES` with `get_provider_sources("google")`
2. ✅ Test all organization connector flows
3. ✅ Deploy to staging

**Risk:** Medium - affects organization connector setup

### Phase 3: Unify Backfill Logic (Higher Risk)
1. ✅ Add `prepare_backfill` to Google plugin
2. ✅ Update `tasks.py` to use unified pattern
3. ✅ Test all backfill scenarios
4. ✅ Deploy to staging, monitor for 24h
5. ✅ Deploy to production

**Risk:** High - affects all connector syncing

### Phase 4: Auto-Generate Types (Low Risk)
1. ✅ Run type generation script
2. ✅ Update frontend imports
3. ✅ Add to build process
4. ✅ Deploy with next frontend release

**Risk:** Low - frontend types only

---

## Timeline

### Conservative (1 week)
- Day 1-2: Create helpers, write tests
- Day 3: Replace GOOGLE_SOURCES
- Day 4-5: Unify backfill logic, extensive testing
- Day 6: Auto-generate types
- Day 7: Buffer for issues

### Aggressive (2-3 days)
- Day 1 AM: Create helpers
- Day 1 PM: Replace GOOGLE_SOURCES, test
- Day 2 AM: Unify backfill logic
- Day 2 PM: Extensive testing
- Day 3: Auto-generate types, final testing

---

## Success Criteria

### After Refactoring:

✅ **Zero `GOOGLE_SOURCES`-style constants in codebase**
- Search: `rg "GOOGLE_SOURCES|MICROSOFT_SOURCES"` returns 0 results

✅ **Zero source_type string matching in core**
- Search: `rg 'if.*source_type.*startswith.*"google"'` returns 0 results (except in plugin code)

✅ **Unified backfill logic**
- Both Google and Microsoft use same code path in `tasks.py`
- Plugin registry handles provider-specific behavior

✅ **Auto-generated frontend types**
- `connector-types.ts` exists and is up-to-date
- `package.json` runs generation on build

✅ **Adding new connector requires 4-5 files:**
1. New connector package
2. Plugin registration (1 line)
3. Run type generation (automatic)
4. Frontend UI component
5. Optional: metadata registry

---

## Maintenance

### Adding Connector #N After Refactoring:

```bash
# 1. Create connector package
mkdir -p backend/app/connectors/slack
# ... implement connector ...

# 2. Register (ONE LINE)
# Edit backend/app/connectors/provider_registry.py:
from app.connectors.slack.plugin import plugin as slack_plugin
register(slack_plugin)

# 3. Generate types (AUTOMATIC)
npm run generate-types

# 4. Add UI (if needed)
# Edit frontend/components/connectors/connector-list.tsx

# Done! 🎉
```

**No changes needed in:**
- ❌ tasks.py
- ❌ router.py (except adding register line)
- ❌ indexer.py
- ❌ sync.py
- ❌ search/
- ❌ acl/

---

## Conclusion

**Effort:** 5-7 hours of focused refactoring
**Benefit:** Every future connector saves 30-60 minutes
**Break-even:** After 5-10 new connectors
**Recommendation:** Do it now before adding more connectors
