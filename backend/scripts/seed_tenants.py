"""
Script to seed development tenants.

Creates 3 dev tenants with their own databases and provisions them.
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Add backend directory to Python path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Determine DB host: use postgres (Docker service name) or localhost for native
# Parse from CONTROL_PLANE_DATABASE_URL if set, otherwise fall back to DB_HOST env var
_db_url = os.getenv("CONTROL_PLANE_DATABASE_URL", "")
if "@postgres:" in _db_url:
    DB_HOST = "postgres"
else:
    DB_HOST = os.getenv("DB_HOST", "localhost")

from app.models.base import Base
from app.models.tenant import Tenant
from app.models.user import User
from app.models.group import Group, GroupMembership
from app.models.oauth_client import OAuthClient, RefreshToken
from app.models.scope import ScopeRegistry
from app.storage.control_plane_db import ControlPlaneSessionLocal
from app.storage.vault_client import vault_client


async def create_dev_tenant(session, name: str, subdomain: str, db_name: str, db_password: str):
    """Create a single development tenant."""
    tenant_id = uuid4()
    db_secret_key = f"kv/tenant-{tenant_id}/db_password"
    
    print(f"\nCreating tenant: {name}")
    print(f"  Tenant ID: {tenant_id}")
    print(f"  Subdomain: {subdomain}")
    print(f"  Database: {db_name}")
    
    # Store password in Vault
    await vault_client.set_secret(db_secret_key, db_password)
    print(f"  [OK] Stored password in Vault: {db_secret_key}")
    
    # Check if tenant already exists
    from sqlalchemy import select
    res = await session.execute(select(Tenant).where(Tenant.subdomain == subdomain))
    existing = res.scalar_one_or_none()
    if existing:
        print(f"  [INFO] Tenant record already exists: {subdomain}")
        # Ensure tenant database tables exist
        tenant_engine = create_async_engine(
            f"postgresql+asyncpg://postgres:postgres@{DB_HOST}:5432/{db_name}"
        )
        async with tenant_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await tenant_engine.dispose()
        print(f"  [OK] Ensured tables in tenant database {db_name}")
        return existing

    # Create tenant record
    tenant = Tenant(
        tenant_id=tenant_id,
        name=name,
        subdomain=subdomain,
        tenancy_mode="isolated_db",
        config={"environment": "development"},
        db_host=DB_HOST,
        db_name=db_name,
        db_user="postgres",
        db_secret_key=db_secret_key,
    )
    
    session.add(tenant)
    print(f"  [OK] Created tenant record")
    
    # Create tenant's database
    # Note: In production, use proper database provisioning
    # For dev, we'll create the database if it doesn't exist
    engine = create_async_engine(
        f"postgresql+asyncpg://postgres:postgres@{DB_HOST}:5432/postgres",
        isolation_level="AUTOCOMMIT",
    )
    
    async with engine.begin() as conn:
        # Check if database exists
        result = await conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
        )
        exists = result.scalar() is not None
        
        if not exists:
            await conn.execute(text(f"CREATE DATABASE {db_name}"))
            print(f"  [OK] Created database: {db_name}")
        else:
            print(f"  [INFO] Database already exists: {db_name}")
    
    await engine.dispose()
    
    # Create tables in tenant database using postgres superuser (dev only)
    # Note: db_password is the Vault secret for a future dedicated DB user;
    # for dev we use the postgres superuser to create tables.
    tenant_engine = create_async_engine(
        f"postgresql+asyncpg://postgres:postgres@{DB_HOST}:5432/{db_name}"
    )
    
    async with tenant_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print(f"  [OK] Created tables in tenant database")
    
    await tenant_engine.dispose()
    
    return tenant


async def seed_tenants():
    """Seed 3 development tenants."""
    print("=" * 80)
    print("SEEDING DEVELOPMENT TENANTS")
    print("=" * 80)
    
    # Create tenants
    async with ControlPlaneSessionLocal() as session:
        tenant_a = await create_dev_tenant(
            session,
            name="Tenant Alpha",
            subdomain="alpha",
            db_name="snyq_tenant_alpha",
            db_password="alpha_password",
        )
        
        tenant_b = await create_dev_tenant(
            session,
            name="Tenant Beta",
            subdomain="beta",
            db_name="snyq_tenant_beta",
            db_password="beta_password",
        )
        
        tenant_c = await create_dev_tenant(
            session,
            name="Tenant Gamma",
            subdomain="gamma",
            db_name="snyq_tenant_gamma",
            db_password="gamma_password",
        )
        
        await session.commit()
    
    print("\n" + "=" * 80)
    print("[OK] SEEDING COMPLETE")
    print("=" * 80)
    print("\nCreated 3 development tenants:")
    print(f"  1. {tenant_a.name} ({tenant_a.subdomain})")
    print(f"  2. {tenant_b.name} ({tenant_b.subdomain})")
    print(f"  3. {tenant_c.name} ({tenant_c.subdomain})")


if __name__ == "__main__":
    asyncio.run(seed_tenants())
