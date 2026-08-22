"""
Per-tenant database: dynamic engine/session factory keyed by tenant_id.

Each tenant gets its own Postgres database (Tier 2 per Vishwas §28.1).
The TenantResolver provides routing info; this module creates the async engine/session.
"""

from typing import Dict, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker

from app.core.exceptions import TenantNotFoundError
from app.storage.postgres_connect import asyncpg_database_url, connect_args_for_host


class TenantDatabaseManager:
    """
    Manages per-tenant database engines and sessions.
    
    Engines are created lazily and cached per tenant_id.
    """

    def __init__(self):
        self._engines: Dict[str, AsyncEngine] = {}
        self._session_factories: Dict[str, async_sessionmaker] = {}

    def get_engine(
        self,
        db_host: str,
        db_name: str,
        db_user: str,
        db_password: str,
        tenant_id: str,
    ) -> AsyncEngine:
        """
        Get or create an async engine for a tenant.
        
        Args:
            db_host: Database host
            db_name: Database name
            db_user: Database user
            db_password: Database password (from Vault)
            tenant_id: Tenant UUID (for caching)
            
        Returns:
            AsyncEngine for the tenant's database.
        """
        if tenant_id in self._engines:
            return self._engines[tenant_id]

        database_url = asyncpg_database_url(db_user, db_password, db_host, db_name)
        engine = create_async_engine(
            database_url,
            echo=False,  # Never log tenant DB URLs in prod
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            connect_args=connect_args_for_host(db_host),
        )
        self._engines[tenant_id] = engine
        return engine

    def get_session_factory(
        self,
        db_host: str,
        db_name: str,
        db_user: str,
        db_password: str,
        tenant_id: str,
    ) -> async_sessionmaker:
        """
        Get or create an async session factory for a tenant.
        
        Args:
            db_host: Database host
            db_name: Database name
            db_user: Database user
            db_password: Database password (from Vault)
            tenant_id: Tenant UUID (for caching)
            
        Returns:
            async_sessionmaker for the tenant's database.
        """
        if tenant_id in self._session_factories:
            return self._session_factories[tenant_id]

        engine = self.get_engine(db_host, db_name, db_user, db_password, tenant_id)
        factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._session_factories[tenant_id] = factory
        return factory

    async def get_session(
        self,
        db_host: str,
        db_name: str,
        db_user: str,
        db_password: str,
        tenant_id: str,
    ) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async session for a tenant's database.
        
        Args:
            db_host: Database host
            db_name: Database name
            db_user: Database user
            db_password: Database password (from Vault)
            tenant_id: Tenant UUID
            
        Yields:
            AsyncSession for the tenant's database.
        """
        factory = self.get_session_factory(db_host, db_name, db_user, db_password, tenant_id)
        async with factory() as session:
            try:
                yield session
            finally:
                await session.close()

    async def close_all(self):
        """Close all tenant engines (for graceful shutdown)."""
        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()
        self._session_factories.clear()


# Global tenant DB manager instance
tenant_db_manager = TenantDatabaseManager()
