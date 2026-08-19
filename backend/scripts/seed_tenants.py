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

# Local Postgres on Windows often fails the asyncpg SSL handshake unless
# SSL is explicitly off (same as tenant_db.py).
_ENGINE_CONNECT = {"ssl": False}

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
from app.models.audit_log import AuditLog  # noqa: F401 — Block N metadata
from app.models.tenant_connector import TenantConnector  # noqa: F401
from app.models.canonical import (  # noqa: F401
    CanonicalDocumentRow,
    IdentityPrincipalRow,
    IdentityGroupRow,
    ACLEntryRow,
    ContainerACLEntryRow,
    ContainerEdgeRow,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.native_auth import native_auth_service
from app.storage.control_plane_db import ControlPlaneSessionLocal
from app.storage.vault_client import vault_client

# Known passwords for Postman / live API / frontend against Docker-seeded Alpha.
# admin@synq.dev stays EmailStr-safe. member@alpha.test is the documented
# read-only employee account; login accepts the reserved .test TLD.
ALPHA_ADMIN_EMAIL = "admin@synq.dev"
ALPHA_ADMIN_PASSWORD = "AlphaAdmin123!"
ALPHA_MEMBER_EMAIL = "member@alpha.test"
ALPHA_MEMBER_PASSWORD = "AlphaMember123!"
# Kept so older docs / filled forms still authenticate.
ALPHA_MEMBER_EMAIL_LEGACY = "member@synq.dev"
ALPHA_SUBDOMAIN = "alpha"


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
            f"postgresql+asyncpg://postgres:postgres@{DB_HOST}:5432/{db_name}",
            connect_args=_ENGINE_CONNECT,
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
        connect_args=_ENGINE_CONNECT,
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
        f"postgresql+asyncpg://postgres:postgres@{DB_HOST}:5432/{db_name}",
        connect_args=_ENGINE_CONNECT,
    )
    
    async with tenant_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print(f"  [OK] Created tables in tenant database")
    
    await tenant_engine.dispose()
    
    return tenant


async def _ensure_user(session, *, email: str, password: str, display_name: str, tenant_id, role: str):
    from sqlalchemy import select

    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        print(f"  [INFO] User already exists: {email}")
        return
    await native_auth_service.create_native_user(
        email=email,
        password=password,
        display_name=display_name,
        tenant_id=tenant_id,
        db_session=session,
        role=role,
        must_change_password=False,
        is_active=True,
    )
    print(f"  [OK] Created {role}: {email}")


async def seed_block_n_users(tenant):
    """Seed Full Admin + member into Alpha's tenant DB for Postman / live login."""
    if tenant.subdomain != "alpha":
        return
    print("\nSeeding Block N native users on tenant alpha...")
    tenant_engine = create_async_engine(
        f"postgresql+asyncpg://postgres:postgres@{DB_HOST}:5432/{tenant.db_name}",
        connect_args=_ENGINE_CONNECT,
    )
    SessionLocal = async_sessionmaker(tenant_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        await _ensure_user(
            session,
            email=ALPHA_ADMIN_EMAIL,
            password=ALPHA_ADMIN_PASSWORD,
            display_name="Alpha Admin",
            tenant_id=tenant.tenant_id,
            role="admin",
        )
        await _ensure_user(
            session,
            email=ALPHA_MEMBER_EMAIL,
            password=ALPHA_MEMBER_PASSWORD,
            display_name="Alpha Member",
            tenant_id=tenant.tenant_id,
            role="member",
        )
        await _ensure_user(
            session,
            email=ALPHA_MEMBER_EMAIL_LEGACY,
            password=ALPHA_MEMBER_PASSWORD,
            display_name="Alpha Member",
            tenant_id=tenant.tenant_id,
            role="member",
        )
    await tenant_engine.dispose()


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

    await seed_block_n_users(tenant_a)
    
    print("\n" + "=" * 80)
    print("[OK] SEEDING COMPLETE")
    print("=" * 80)
    print("\nCreated 3 development tenants:")
    print(f"  1. {tenant_a.name} ({tenant_a.subdomain})")
    print(f"  2. {tenant_b.name} ({tenant_b.subdomain})")
    print(f"  3. {tenant_c.name} ({tenant_c.subdomain})")
    print("\nBlock N live login (Postman / curl) against tenant alpha:")
    print(f"  POST /auth/login")
    print(f"  admin:  {ALPHA_ADMIN_EMAIL} / {ALPHA_ADMIN_PASSWORD}")
    print(f"  member: {ALPHA_MEMBER_EMAIL} / {ALPHA_MEMBER_PASSWORD}")
    print(f"  tenant_subdomain: {ALPHA_SUBDOMAIN}")


if __name__ == "__main__":
    asyncio.run(seed_tenants())
