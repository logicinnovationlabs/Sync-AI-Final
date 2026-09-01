# Connector Architecture Analysis

## Question: Is the Architecture Structured for Easy Extension?

**Answer: YES, but with some improvements needed** ✅ (mostly) ⚠️ (some hardcoding)

The architecture follows a **plugin pattern** which is good, but there are a few places where source types are hardcoded that should be abstracted.

---

## Current State: Adding a New Connector

### What's Well-Structured ✅

1. **Plugin System** (`provider_registry.py`)
   - Central registration of providers
   - One import + register line to add new connector
   - Automatic routing to Celery queues

2. **Base Connector Contract** (`base_connector.py`)
   - Abstract base class all connectors implement
   - Unified `UnifiedDocument` format
   - Standard methods: `fetch_delta()`, `fetch_deletions()`, etc.

3. **Provider Plugin Protocol** (`plugin_base.py`)
   - Standard callbacks: OAuth, webhooks, backfill
   - Core files don't need to know connector specifics

4. **ACL Term Generation** (after our fix)
   - Unified `generate_acl_terms_for_user()` works for ANY connector
   - No connector-specific ACL logic needed

### What Needs Improvement ⚠️

1. **Hardcoded Source Type Lists**
   - `GOOGLE_SOURCES = ("google_drive", "google_gmail")` in multiple files
   - Should be queried from plugin registry instead

2. **Connector-Specific Logic Scattered**
   - Some `if source_type.startswith("google_")` checks
   - Should use plugin.owns_source() or plugin queries

3. **Frontend Type Definitions**
   - `BackendSourceType` in frontend needs manual updates
   - Could be auto-generated from backend

---

## Files That SHOULD Change (Well-Structured)

### For a New Connector (e.g., Dropbox):

**1. Create New Connector Package** (NEW FILES)
```
backend/app/connectors/dropbox/
├── __init__.py
├── plugin.py              # Plugin registration
├── oauth.py               # OAuth flow
├── services/
│   └── dropbox_service.py # Connector implementation
├── token_store.py         # Token management
└── webhooks.py            # Webhook handlers (optional)
```

**2. Register in Provider Registry** (1 FILE)
```python
# backend/app/connectors/provider_registry.py
from app.connectors.dropbox.plugin import plugin as dropbox_plugin
register(dropbox_plugin)
```

**3. Update Frontend Types** (1 FILE)
```typescript
// frontend/lib/api/connectors.ts
export type BackendSourceType =
  | "google_drive"
  | "google_gmail"
  | "onedrive"
  | "outlook"
  | "dropbox"  // Add this
```

**4. Update Connector Metadata Registry** (1 FILE - OPTIONAL)
```python
# backend/app/services/registry.py
# Add metadata for Dropbox if needed
```

**Total: ~2-3 shared files + your new connector package**

---

## Files That SHOULDN'T Change (But Currently Might)

These files should NOT need changes for new connectors, but currently might due to hardcoding:

### ⚠️ Needs Refactoring:

**1. `backend/app/connectors/router.py`**
```python
# CURRENT (hardcoded):
GOOGLE_SOURCES = ("google_drive", "google_gmail")

# SHOULD BE (dynamic):
def get_sources_for_provider(provider_id: str):
    plugin = provider_registry.get(provider_id)
    return plugin.sources if plugin else ()
```

**2. `backend/app/workers/tasks.py`**
```python
# CURRENT (hardcoded):
if source_type.startswith("google_"):
    # Google-specific logic

# SHOULD BE (plugin-based):
plugin = provider_registry.get_by_source(source_type)
if plugin and plugin.provider_id == "google":
    # Use plugin methods
```

**3. `backend/app/services/assistant/infrastructure/connector_context.py`**
```python
# Builds "Connected integrations" text for chat
# Should query provider_registry.all_plugins() instead of hardcoding
```

---

## Recommended Improvements

### 1. Remove Hardcoded Source Lists

**Before:**
```python
# connector/router.py
GOOGLE_SOURCES = ("google_drive", "google_gmail")

for source_type in GOOGLE_SOURCES:
    # Do something
```

**After:**
```python
# connector/router.py
def get_provider_sources(provider_id: str) -> Tuple[str, ...]:
    plugin = provider_registry.get(provider_id)
    return plugin.sources if plugin else ()

for source_type in get_provider_sources("google"):
    # Do something
```

### 2. Replace `if source_type.startswith("google_")` Pattern

**Before:**
```python
if source_type.startswith("google_"):
    token_store = PersistentGoogleTokenStore(tenant_id)
    # ...
elif source_type in ("onedrive", "outlook"):
    plugin = provider_registry.get_by_source(source_type)
    # ...
```

**After:**
```python
plugin = provider_registry.get_by_source(source_type)
if not plugin:
    raise ValueError(f"Unknown source_type: {source_type}")

auth = plugin.prepare_backfill(tenant_id, source_type, principal_id)
token_store = auth.token_store
# Unified handling
```

### 3. Auto-Generate Frontend Types

**Create:** `backend/scripts/generate_frontend_types.py`
```python
from app.connectors import provider_registry

def generate_source_types():
    plugins = provider_registry.all_plugins()
    sources = []
    for plugin in plugins:
        sources.extend(plugin.sources)
    
    ts_type = " | ".join(f'"{s}"' for s in sources)
    return f"export type BackendSourceType = {ts_type};"

# Write to frontend/lib/api/connectors.ts
```

---

## Ideal State: Adding a New Connector

### Files to Change (4-5 files):

1. **Create connector package** (`backend/app/connectors/dropbox/`)
   - `plugin.py` - Define plugin
   - `oauth.py` - OAuth implementation
   - `services/dropbox_service.py` - Connector implementation
   - `token_store.py` - Token management

2. **Register plugin** (`backend/app/connectors/provider_registry.py`)
   - One import line
   - One `register(dropbox_plugin)` line

3. **Update frontend type** (`frontend/lib/api/connectors.ts`)
   - Add `"dropbox"` to `BackendSourceType` union
   - (Or auto-generate this)

4. **Add connector metadata** (`backend/app/services/registry.py`)
   - Optional: Add allowed metadata keys for Dropbox

5. **Add frontend UI** (`frontend/components/connectors/connector-list.tsx`)
   - Add logo and display name for Dropbox

**That's it!** No changes to:
- ❌ `tasks.py` - Uses plugin system
- ❌ `indexer.py` - Connector-agnostic
- ❌ `router.py` - Uses plugin system
- ❌ `sync.py` - Uses BaseConnector interface
- ❌ `search/` - Connector-agnostic

---

## Current Reality Check

### Adding Dropbox Today Would Require:

**Necessary Changes (Good):**
1. Create `connectors/dropbox/` package
2. Register in `provider_registry.py`
3. Update frontend `BackendSourceType`
4. Add connector metadata (optional)
5. Add frontend UI component

**Unnecessary Changes (Needs Refactoring):**
6. ⚠️ Update `GOOGLE_SOURCES` references if you have multi-source provider
7. ⚠️ Possibly update `if source_type.startswith()` checks

**Estimate: ~5-7 files currently, should be ~4-5 files**

---

## Action Plan for Perfect Architecture

### Phase 1: Remove Hardcoded Lists (1-2 hours)
- [ ] Replace `GOOGLE_SOURCES` with dynamic queries
- [ ] Create helper: `get_provider_sources(provider_id)`
- [ ] Update all references in `router.py`

### Phase 2: Unify Plugin-Based Checks (2-3 hours)
- [ ] Replace `if source_type.startswith("google_")` with plugin queries
- [ ] Use `plugin.prepare_backfill()` uniformly in `tasks.py`
- [ ] Remove provider-specific branching

### Phase 3: Auto-Generate Frontend Types (1 hour)
- [ ] Create `scripts/generate_frontend_types.py`
- [ ] Add to pre-commit hook or CI
- [ ] Update build process

### Phase 4: Document Connector Development (1 hour)
- [ ] Create `CONNECTOR_DEVELOPMENT_GUIDE.md`
- [ ] Add template files for new connectors
- [ ] Document plugin contract

**Total Effort: 5-7 hours to reach ideal state**

---

## Comparison: Before vs. After Refactoring

### Adding Slack Connector

**Current (7 files):**
1. ✅ Create `connectors/slack/` package
2. ✅ Register in `provider_registry.py`
3. ✅ Update frontend `BackendSourceType`
4. ⚠️ Update `GOOGLE_SOURCES`-style list if needed
5. ⚠️ Fix `if source_type.startswith()` checks in `tasks.py`
6. ⚠️ Update `connector_context.py` for chat display
7. ✅ Add frontend UI

**After Refactoring (4 files):**
1. ✅ Create `connectors/slack/` package
2. ✅ Register in `provider_registry.py`
3. ✅ Run `python scripts/generate_frontend_types.py` (auto-updates frontend)
4. ✅ Add frontend UI

---

## Verdict

### Current State: 6-7/10 ⭐⭐⭐⭐⭐⭐⭐☆☆☆

**Strengths:**
- ✅ Plugin system exists and works well
- ✅ Base connector contract is clean
- ✅ Provider registry is well-designed
- ✅ ACL generation is unified (after our fix)

**Weaknesses:**
- ⚠️ Some hardcoded source type lists
- ⚠️ Some connector-specific if/else branching
- ⚠️ Frontend types require manual updates

### After Refactoring: 9-10/10 ⭐⭐⭐⭐⭐⭐⭐⭐⭐☆

**Improvements:**
- ✅ 100% dynamic source type handling
- ✅ Zero connector-specific branching in core
- ✅ Auto-generated frontend types
- ✅ Add connector in 4-5 files maximum

---

## Conclusion

**Your architecture IS mostly well-structured**, but needs ~5-7 hours of refactoring to reach the ideal "4-5 files only" goal for new connectors.

**Right now:** Adding a new connector requires changes to **~6-7 files**
- 4 necessary (connector package, registry, frontend)
- 2-3 unnecessary (hardcoded lists, branching logic)

**After refactoring:** Would require changes to **~4 files**
- 3 necessary (connector package, registry, frontend UI)
- 1 auto-generated (frontend types)

The foundation is solid. The improvements are straightforward and well worth the investment for long-term maintainability.

---

## Immediate Next Steps

### Option 1: Accept Current State (6-7 files per connector)
- Continue adding connectors with current architecture
- ~5-10 extra minutes per connector due to scattered changes

### Option 2: Refactor First (Recommended)
- Spend 5-7 hours improving architecture
- Future connectors take only 4 files
- Save time on connector #3 and beyond

### Option 3: Incremental Improvement
- Fix hardcoding as you encounter it
- Gradually improve architecture
- Lower upfront cost but slower progress

**My Recommendation: Option 2** - The refactoring is straightforward and pays for itself after 2-3 new connectors.
