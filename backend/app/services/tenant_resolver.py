"""
TenantResolver: the core tenant routing service.

Per Vishwas §28.2:
1. Resolves tenant_id -> routing metadata (DB host, name, user)
2. Fetches password from Vault (never from the tenants table)
3. Caches resolved routing per tenant with 30-60 min TTL
4. Cache is PARTITIONED per tenant (never shared)

Critical for Signoff A6 and A7.
"""

from typing import Optional
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import TenantNotFoundError, VaultError
from app.models.tenant import Tenant
from app.storage import control_plane_db as control_plane_db
from app.storage.redis_client import redis_client
from app.storage.vault_client import vault_client


@dataclass
class TenantRouting:
    """
    Tenant routing information (what you need to connect to a tenant's database).
    
    This is returned by TenantResolver and passed to TenantDatabaseManager.
    """

    tenant_id: str
    db_host: str
    db_name: str
    db_user: str
    db_password: str  # Fetched from Vault at runtime, never persisted
    config: dict


class TenantResolver:
    """
    Tenant metadata resolver with per-tenant caching.
    
    This is the service Vishwas described in §28.2: every other service
    calls this to resolve a tenant's connection details, with a per-tenant
    cache in front of it (not a shared cache).
    """

    def __init__(self):
        self.cache_ttl = settings.tenant_cache_ttl_seconds

    async def resolve(self, tenant_id: str) -> TenantRouting:
        """
        Resolve a tenant's routing information.
        
        Process:
        1. Check per-tenant cache (key: 'routing')
        2. On miss: query tenants table
        3. Fetch db_password from Vault using tenant.db_secret_key
        4. Cache the result under tenant:{tenant_id}:routing (A7)
        5. Return TenantRouting
        
        Args:
            tenant_id: Tenant UUID as string
            
        Returns:
            TenantRouting with all connection details.
            
        Raises:
            TenantNotFoundError if tenant doesn't exist.
            VaultError if secret retrieval fails.
        """
        # Step 1: Check per-tenant cache (A7: namespace-partitioned)
        cached = await redis_client.get_json(tenant_id, "routing")
        if cached:
            secret_key = cached.get("db_secret_key")
            cached.pop("db_password", None)
            if secret_key:
                try:
                    cached["db_password"] = await vault_client.get_secret(secret_key)
                    return TenantRouting(
                        tenant_id=cached["tenant_id"],
                        db_host=cached["db_host"],
                        db_name=cached["db_name"],
                        db_user=cached["db_user"],
                        db_password=cached["db_password"],
                        config=cached.get("config") or {},
                    )
                except Exception:
                    pass

        # Step 2: Query control-plane database
        async with control_plane_db.ControlPlaneSessionLocal() as session:
            stmt = select(Tenant).where(Tenant.tenant_id == UUID(tenant_id))
            result = await session.execute(stmt)
            tenant = result.scalar_one_or_none()

        if not tenant:
            raise TenantNotFoundError(tenant_id)

        # Step 3: Fetch password from Vault (A6: never stored in DB)
        try:
            db_password = await vault_client.get_secret(tenant.db_secret_key)
        except Exception as e:
            raise VaultError(f"Failed to retrieve secret for tenant {tenant_id}: {e}")

        routing = TenantRouting(
            tenant_id=str(tenant.tenant_id),
            db_host=tenant.db_host,
            db_name=tenant.db_name,
            db_user=tenant.db_user,
            db_password=db_password,
            config=tenant.config,
        )

        # Cache NAMES only — never the password (§28.2)
        await redis_client.set_json(
            tenant_id,
            "routing",
            {
                "tenant_id": routing.tenant_id,
                "db_host": routing.db_host,
                "db_name": routing.db_name,
                "db_user": routing.db_user,
                "db_secret_key": tenant.db_secret_key,
                "config": routing.config,
            },
            ex=self.cache_ttl,
        )

        return routing

    async def invalidate_cache(self, tenant_id: str) -> None:
        """
        Invalidate the cached routing for a tenant.
        
        Args:
            tenant_id: Tenant UUID as string
        """
        await redis_client.delete(tenant_id, "routing")


# Global resolver instance
tenant_resolver = TenantResolver()
