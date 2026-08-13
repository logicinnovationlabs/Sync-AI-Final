"""Tenant-aware Neo4j connection manager with TTL cache."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TenantNeo4jConfig:
    uri: str
    user: str
    password: str
    database: str
    tenant_id: str


@dataclass
class _CacheEntry:
    driver: Any
    config: TenantNeo4jConfig
    expires_at: float


class Neo4jClientManager:
    """
    Per-tenant driver cache (TTL 30–60 min).

    Isolation model: one Neo4j database per tenant named
    ``{neo4j_database_prefix}{sanitized_tenant_id}``.
    Credentials may come from Block D vault in production; defaults from settings.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, _CacheEntry] = {}
        self._admin_driver = None
        self._single_db_mode = False

    @staticmethod
    def database_name(tenant_id: str) -> str:
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in tenant_id.lower())
        return f"{settings.neo4j_database_prefix}{safe}"

    def _resolve_config(self, tenant_id: str) -> TenantNeo4jConfig:
        """
        Resolve Neo4j endpoint for tenant.

        Production: call Block D tenant metadata + vault for password.
        Dev/test: derive database name from tenant_id; shared Aura/self-hosted creds.
        """
        return TenantNeo4jConfig(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=self.database_name(tenant_id),
            tenant_id=tenant_id,
        )

    def _get_driver(self):
        from neo4j import GraphDatabase

        if self._admin_driver is None:
            self._admin_driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
        return self._admin_driver

    def ensure_database(self, tenant_id: str) -> TenantNeo4jConfig:
        """Create Neo4j database for tenant if missing (Community may no-op)."""
        cfg = self._resolve_config(tenant_id)
        if self._single_db_mode:
            return TenantNeo4jConfig(
                uri=cfg.uri,
                user=cfg.user,
                password=cfg.password,
                database="neo4j",
                tenant_id=tenant_id,
            )
        try:
            driver = self._get_driver()
            with driver.session(database="system") as session:
                exists = session.run(
                    "SHOW DATABASES YIELD name WHERE name = $name RETURN name",
                    name=cfg.database,
                ).single()
                if not exists:
                    session.run(f"CREATE DATABASE `{cfg.database}` IF NOT EXISTS")
                    logger.info("Created Neo4j database %s", cfg.database)
        except Exception as exc:
            # Aura free / Community single-DB: fall back to default database
            logger.warning(
                "Could not create/select tenant DB %s (%s); using default database",
                cfg.database,
                exc,
            )
            self._single_db_mode = True
            cfg = TenantNeo4jConfig(
                uri=cfg.uri,
                user=cfg.user,
                password=cfg.password,
                database="neo4j",
                tenant_id=tenant_id,
            )
        return cfg

    def get_session_config(self, tenant_id: str) -> TenantNeo4jConfig:
        now = time.time()
        entry = self._cache.get(tenant_id)
        if entry and entry.expires_at > now:
            return entry.config

        cfg = self.ensure_database(tenant_id)
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(cfg.uri, auth=(cfg.user, cfg.password))
        self._cache[tenant_id] = _CacheEntry(
            driver=driver,
            config=cfg,
            expires_at=now + settings.neo4j_cache_ttl_seconds,
        )
        return cfg

    def get_driver(self, tenant_id: str):
        now = time.time()
        entry = self._cache.get(tenant_id)
        if entry and entry.expires_at > now:
            return entry.driver, entry.config
        self.get_session_config(tenant_id)
        entry = self._cache[tenant_id]
        return entry.driver, entry.config

    def invalidate(self, tenant_id: str) -> None:
        entry = self._cache.pop(tenant_id, None)
        if entry:
            try:
                entry.driver.close()
            except Exception:
                pass

    def close_all(self) -> None:
        for tid in list(self._cache.keys()):
            self.invalidate(tid)
        if self._admin_driver is not None:
            try:
                self._admin_driver.close()
            except Exception:
                pass
            self._admin_driver = None

    def health(self) -> Tuple[bool, str]:
        try:
            driver = self._get_driver()
            driver.verify_connectivity()
            return True, "neo4j-ok"
        except Exception as exc:
            return False, str(exc)


# Process-wide manager
_manager: Optional[Neo4jClientManager] = None


def get_neo4j_manager() -> Neo4jClientManager:
    global _manager
    if _manager is None:
        _manager = Neo4jClientManager()
    return _manager
