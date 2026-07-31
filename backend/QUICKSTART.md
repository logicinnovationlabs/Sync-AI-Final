# Quick Start Guide - SnyQ Backend (Block A)

## 2-Minute Automated Setup (Recommended)

### Linux/Mac

```bash
cd backend
chmod +x setup.sh
./setup.sh
docker-compose up -d
python scripts/seed_tenants.py
```

### Windows

```cmd
cd backend
setup.bat
docker-compose up -d
python scripts\seed_tenants.py
```

---

## 5-Minute Manual Setup

### 1. Start Services

```bash
cd backend
docker-compose up -d
```

Wait for postgres and redis to be healthy (about 10-15 seconds).

### 2. Generate JWT Keys

**With Poetry:**
```bash
poetry install
poetry run python scripts/generate_keys.py
```

**With pip/venv:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python scripts/generate_keys.py
```

### 3. Seed Dev Tenants

**With Poetry:**
```bash
poetry run python scripts/seed_tenants.py
```

**With pip/venv:**
```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
python scripts/seed_tenants.py
```

This creates 3 tenants: `alpha`, `beta`, `gamma`.

### 4. Test the API

```bash
# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs
```

### 5. Run Signoff Tests

**With Poetry:**
```bash
poetry run pytest tests/test_signoff.py -v
```

**With pip/venv:**
```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements-dev.txt  # Install test dependencies
pytest tests/test_signoff.py -v
```

**Critical**: All A1–A7 tests must PASS for signoff.

---

## Issuing Your First Token (Manual Test)

```python
import asyncio
from app.services.token_service import token_service

async def test_token():
    token = await token_service.issue_access_token(
        tenant_id="your-tenant-id-here",
        principal_id="test-user-123",
        scopes=["search.read", "document.read"],
    )
    print(f"Token: {token}")
    
    payload = await token_service.validate_token(token)
    print(f"Payload: {payload}")

asyncio.run(test_token())
```

---

## Creating a New Tenant

### Via API (Dev/Test)

```bash
curl -X POST http://localhost:8000/api/v1/admin/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Tenant",
    "subdomain": "test",
    "db_host": "localhost",
    "db_name": "snyq_tenant_test",
    "db_user": "postgres",
    "db_password": "test_password"
  }'
```

### Via Script

Edit `scripts/seed_tenants.py` and add your tenant, then run:

```bash
poetry run python scripts/seed_tenants.py
```

---

## Common Tasks

### Run All Tests

**With Poetry:**
```bash
poetry run pytest -v
```

**With pip/venv:**
```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
pytest -v
```

### Check Code Quality

**With Poetry:**
```bash
poetry run black app/ tests/
poetry run ruff check app/ tests/
```

**With pip/venv:**
```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
black app/ tests/
ruff check app/ tests/
```

### View Logs

```bash
docker-compose logs -f app
```

### Stop Services

```bash
docker-compose down
```

### Reset Database

```bash
docker-compose down -v
docker-compose up -d
poetry run python scripts/seed_tenants.py
```

---

## Troubleshooting

### "Connection refused" errors

Make sure Postgres and Redis are running:

```bash
docker-compose ps
```

### "Token validation failed"

Regenerate keys:

```bash
poetry run python scripts/generate_keys.py
```

### Tests failing

Check environment variables:

```bash
cp .env.example .env
# Edit .env with correct values
```

---

## Next: Adding Your First Connector (Block B Preview)

```python
# app/connectors/my_connector/connector.py
from app.core.base_connector import BaseConnector, DeltaResult, UnifiedDocument

class MyConnector(BaseConnector):
    def get_source_type(self) -> str:
        return "my_source"
    
    async def get_valid_token(self) -> str:
        # OAuth token refresh logic
        pass
    
    async def fetch_delta(self, since, cursor) -> DeltaResult:
        # Fetch changed documents
        pass
    
    async def fetch_deleted_ids(self, since, cursor):
        # Fetch deleted IDs
        raise NotImplementedError()
    
    async def transform(self, raw_documents) -> List[UnifiedDocument]:
        # Transform to canonical format
        pass
```

That's it! The registry auto-discovers your connector. No core file changes needed.

---

## Documentation

- **Full README**: `backend/README.md`
- **Signoff Report**: `backend/SIGNOFF.md`
- **Architecture PDF**: `Glean_Arch_made_by_Glean_v1_3.pdf`
- **API Docs**: http://localhost:8000/docs (when running)

---

## Support

For issues, contact the SnyQ engineering team or consult the architecture document.
