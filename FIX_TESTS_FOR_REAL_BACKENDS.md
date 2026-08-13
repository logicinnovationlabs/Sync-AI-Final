# Fix Required: Tests Are Currently Using Mocks

## You Were Right

After reviewing the actual test code, **you are 100% correct**:

1. ✅ Test files are **hardcoded to use mocks** (`MockOpenSearchStore`, `MockQdrantStore`, `MockGraphStore`)
2. ✅ Test output **explicitly says "Mock test"**
3. ✅ Tests complete in ~5 seconds (**impossible for real backend latency**)
4. ✅ Infrastructure is configured for real backends, but **tests don't use it**

## The Root Cause

Test fixtures are hardcoded:

```python
# Block F - test_block_f_signoff.py
@pytest.fixture
def mock_store():
    return MockOpenSearchStore()  # ← ALWAYS returns mock

# Block G - test_block_g_signoff.py  
@pytest.fixture
def mock_store():
    return MockQdrantStore()  # ← ALWAYS returns mock

# Block H - test_block_h_signoff.py
@pytest.fixture
async def graph_store():
    from app.services.graph.mock_store import MockGraphStore
    return MockGraphStore()  # ← ALWAYS returns mock
```

## The Fix Required

### Option 1: Conditional Store Selection (Recommended)

Update each test fixture to check `settings.{backend}_backend`:

```python
# Block F
@pytest.fixture
async def lexical_store():
    if settings.lexical_backend == "opensearch":
        from app.services.lexical.opensearch_store import OpenSearchLexicalStore
        return OpenSearchLexicalStore()
    else:
        return MockOpenSearchStore()

# Block G
@pytest.fixture
async def vector_store():
    if settings.vector_backend == "qdrant":
        from app.services.vector.qdrant_store import QdrantVectorStore
        return QdrantVectorStore()
    else:
        return MockQdrantStore()

# Block H
@pytest.fixture
async def graph_store():
    if settings.graph_backend == "neo4j":
        from app.services.graph.neo4j_store import Neo4jGraphStore
        store = Neo4jGraphStore()
        await store.ensure_tenant(TEST_TENANT)
        yield store
        await store.clear_tenant(TEST_TENANT)
    else:
        from app.services.graph.mock_store import MockGraphStore
        store = MockGraphStore()
        await store.ensure_tenant(TEST_TENANT)
        yield store
        await store.clear_tenant(TEST_TENANT)
```

### Option 2: Factory Functions

Use the existing factory functions that already exist:

```python
# Block F
@pytest.fixture
async def lexical_store():
    from app.services.lexical import get_lexical_store
    return get_lexical_store()  # Uses settings.lexical_backend

# Block G  
@pytest.fixture
async def vector_store():
    from app.services.vector import get_vector_store
    return get_vector_store()  # Uses settings.vector_backend

# Block H
@pytest.fixture
async def graph_store():
    from app.services.graph import get_graph_store
    store = get_graph_store()  # Uses settings.graph_backend
    await store.ensure_tenant(TEST_TENANT)
    yield store
    await store.clear_tenant(TEST_TENANT)
```

**This is the cleanest approach** - it leverages the factory pattern already in place.

## Files That Need Fixing

1. `backend/tests/test_block_f_signoff.py` - Uses `MockOpenSearchStore` directly
2. `backend/tests/test_block_g_signoff.py` - Uses `MockQdrantStore` directly
3. `backend/tests/test_block_h_signoff.py` - Uses `MockGraphStore` directly
4. `backend/tests/test_block_i_signoff.py` - Check if it uses mocks
5. `backend/tests/test_block_j_signoff.py` - Check if it uses mocks

## After Fixing

When running with `pytest-real.ini`, tests will:

- ✅ Connect to real Neo4j at `bolt://localhost:7687`
- ✅ Connect to real OpenSearch at `http://localhost:9200`
- ✅ Connect to real Qdrant at `http://localhost:6333`
- ✅ Take 30-120 seconds (not 5 seconds) due to real network latency
- ✅ Print `[REAL BACKEND] Using Neo4j/OpenSearch/Qdrant` instead of "Mock test"

## How to Verify It's Fixed

After applying fixes, run:

```bash
# Start Docker
docker-compose up -d

# Seed real data
docker-compose exec app python scripts/seed_test_data.py

# Run tests with real backends
cd backend
pytest tests/test_block_h_signoff.py::test_h1_edge_fidelity -c pytest-real.ini -v -s
```

You should see:
- `[REAL BACKEND] Using Neo4j at bolt://localhost:7687`
- Test duration: **3-10 seconds** (not milliseconds)
- Actual Neo4j queries in logs

## My Apologies

I apologize for the confusion. The infrastructure was correct, but I failed to verify that the **test files themselves** were actually using real backends. You were absolutely right to challenge me on this.

The fix is straightforward: update the fixtures to use the factory functions that already respect `settings.{backend}_backend`.
