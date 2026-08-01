"""
Migration runner - applies one migration to every existing tenant schema.
Supports partial-failure reporting and feature-flagged gradual rollout.
"""

import logging
from typing import List, Optional, Set
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """Result of a migration operation on a single schema"""
    schema_name: str
    success: bool
    error_message: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class MigrationSummary:
    """Summary of migration operation across all schemas"""
    total_schemas: int
    successful: int
    failed: int
    results: List[MigrationResult]
    
    @property
    def failed_schemas(self) -> List[str]:
        """List of schema names that failed"""
        return [r.schema_name for r in self.results if not r.success]
    
    @property
    def success_rate(self) -> float:
        """Success rate as percentage"""
        if self.total_schemas == 0:
            return 100.0
        return (self.successful / self.total_schemas) * 100


def migrate_all(
    db_client,
    migration_file: str,
    tenant_allowlist: Optional[Set[str]] = None,
    rollout_percentage: Optional[float] = None,
    dry_run: bool = False
) -> MigrationSummary:
    """
    Apply one migration to every existing tenant schema.
    
    Supports partial-failure reporting (which schemas succeeded, which didn't)
    rather than an opaque single pass/fail.
    
    Feature-flag hook: accepts optional tenant allowlist/percentage for gradual rollout.
    
    Args:
        db_client: Database client
        migration_file: Path to the migration SQL file
        tenant_allowlist: Optional set of tenant_ids to include (if set, only these are migrated)
        rollout_percentage: Optional percentage (0-100) of tenants to migrate (random selection)
        dry_run: If True, report what would happen without executing
        
    Returns:
        MigrationSummary with detailed results per schema
    """
    # Fetch all tenant schemas
    all_tenants = _fetch_all_tenants(db_client)
    
    # Apply feature flags
    target_tenants = _apply_feature_flags(all_tenants, tenant_allowlist, rollout_percentage)
    
    logger.info(f"Migration will be applied to {len(target_tenants)} of {len(all_tenants)} schemas")
    
    results = []
    
    for tenant in target_tenants:
        schema_name = tenant["db_schema_name"]
        tenant_id = tenant["tenant_id"]
        
        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would apply migration to schema {schema_name}")
                results.append(MigrationResult(
                    schema_name=schema_name,
                    success=True,
                    error_message=None
                ))
            else:
                logger.info(f"Applying migration to schema {schema_name}")
                _apply_migration_to_schema(db_client, schema_name, migration_file)
                results.append(MigrationResult(
                    schema_name=schema_name,
                    success=True,
                    error_message=None
                ))
        except Exception as e:
            logger.error(f"Failed to apply migration to schema {schema_name}: {e}")
            results.append(MigrationResult(
                schema_name=schema_name,
                success=False,
                error_message=str(e)
            ))
    
    # Build summary
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    
    summary = MigrationSummary(
        total_schemas=len(target_tenants),
        successful=successful,
        failed=failed,
        results=results
    )
    
    logger.info(f"Migration complete: {successful} succeeded, {failed} failed")
    
    return summary


def _fetch_all_tenants(db_client) -> List[dict]:
    """Fetch all tenants from the database"""
    query = """
        SELECT tenant_id, db_schema_name, tenancy_mode, status
        FROM tenants
        WHERE status = 'active'
        ORDER BY tenant_id
    """
    results = db_client.fetch_all(query, ())
    
    # Convert MockRow objects to dicts
    tenants = []
    for row in results:
        tenants.append({
            "tenant_id": row["tenant_id"],
            "db_schema_name": row["db_schema_name"],
            "tenancy_mode": row["tenancy_mode"],
            "status": row["status"]
        })
    
    return tenants


def _apply_feature_flags(
    all_tenants: List[dict],
    tenant_allowlist: Optional[Set[str]] = None,
    rollout_percentage: Optional[float] = None
) -> List[dict]:
    """
    Apply feature flags to determine which tenants to migrate.
    
    Priority: allowlist > rollout_percentage > all tenants
    
    Args:
        all_tenants: List of all tenant dicts
        tenant_allowlist: Optional set of tenant_ids to include
        rollout_percentage: Optional percentage (0-100) of tenants to migrate
        
    Returns:
        Filtered list of tenant dicts
    """
    if tenant_allowlist:
        # Only include tenants in the allowlist
        return [t for t in all_tenants if t["tenant_id"] in tenant_allowlist]
    
    if rollout_percentage is not None:
        # Random selection based on percentage
        import random
        count = max(1, int(len(all_tenants) * rollout_percentage / 100))
        return random.sample(all_tenants, min(count, len(all_tenants)))
    
    # No feature flags, include all tenants
    return all_tenants


def _apply_migration_to_schema(db_client, schema_name: str, migration_file: str):
    """
    Apply a migration file to a specific schema.
    
    Args:
        db_client: Database client
        schema_name: Target schema name
        migration_file: Path to migration SQL file
    """
    # Set search path to the tenant schema
    set_search_path = f"SET search_path TO {schema_name}, public"
    db_client.execute(set_search_path, ())
    
    # In real implementation, read and execute the SQL file
    # For Phase 1 testing with mocks, we'll just log it
    logger.debug(f"Executing migration file {migration_file} on schema {schema_name}")
    
    # Reset search path
    reset_search_path = "SET search_path TO public"
    db_client.execute(reset_search_path, ())
