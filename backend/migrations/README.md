# Alembic Configuration

This directory contains database migration scripts for the SnyQ Platform.

## Important Notes

### Per-Tenant Migrations

Since we use **Tier 2 tenancy** (one database per tenant), migrations must be run:

1. **Once** for the control-plane database (`tenants` table)
2. **Once per tenant** for each tenant's own database

### Running Migrations

#### Control-Plane DB (Tenants Table)

```bash
# Generate migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head
```

#### Per-Tenant DB

For each tenant, you must run migrations against their specific database.

**Script to migrate all tenants** (to be created):

```python
# scripts/migrate_all_tenants.py
import asyncio
from app.services.tenant_resolver import tenant_resolver
from app.storage.control_plane_db import ControlPlaneSessionLocal
from sqlalchemy import select
from app.models.tenant import Tenant

async def migrate_all_tenants():
    async with ControlPlaneSessionLocal() as session:
        stmt = select(Tenant)
        result = await session.execute(stmt)
        tenants = result.scalars().all()
        
        for tenant in tenants:
            print(f"Migrating tenant: {tenant.name} ({tenant.tenant_id})")
            # Run alembic upgrade against tenant.db_name
            # ... (implementation depends on your migration strategy)

if __name__ == "__main__":
    asyncio.run(migrate_all_tenants())
```

---

## Migration Strategy

1. **Never** break existing tenant databases
2. Use feature flags for schema changes that require data backfill
3. Test migrations on a dev tenant first
4. Roll out migrations gradually (not all tenants at once)

---

## Configuration

Edit `alembic.ini` to point to the correct database URL for migration generation.

For control-plane:
```ini
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/control_plane
```

For per-tenant (during development):
```ini
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/snyq_tenant_alpha
```
