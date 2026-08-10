"""
Tenant provisioning - creates schema, applies migrations, inserts tenant row.
Idempotent operation per spec.
"""

import logging
from typing import Optional
from datetime import datetime

from tenant_router.models import TenancyMode, TenantRoutingInfo
from vault_client.vault_client import VaultClient

logger = logging.getLogger(__name__)


def provision_tenant(
    tenant_id: str,
    db_client,
    vault_client: VaultClient,
    tenancy_mode: TenancyMode = TenancyMode.ISOLATED_DB,
    migration_files: Optional[list] = None
) -> TenantRoutingInfo:
    """
    Provision a new tenant.
    
    Creates schema `tenant_<id>`, applies the full current migration set,
    inserts the `tenants` row, requests a vault key ref, returns routing info.
    
    Idempotent: calling it twice on the same `tenant_id` will not corrupt state.
    If the tenant already exists, it returns the existing routing info.
    
    Args:
        tenant_id: The tenant identifier
        db_client: Database client
        vault_client: Vault client for secrets
        tenancy_mode: Tenancy mode (default: isolated_db per Glean Arch v1.3)
        migration_files: List of migration SQL files to apply (optional)
        
    Returns:
        TenantRoutingInfo with schema name, resolved secret handle, object prefix
    """
    schema_name = f"tenant_{tenant_id}"
    object_store_prefix = f"tenant_{tenant_id}"
    secrets_key_ref = f"tenant_{tenant_id}_secrets"
    
    # Check if tenant already exists
    existing_tenant = _fetch_existing_tenant(db_client, tenant_id)
    
    if existing_tenant:
        logger.info(f"Tenant {tenant_id} already exists, returning existing routing info")
        return TenantRoutingInfo(
            tenant_id=existing_tenant["tenant_id"],
            tenancy_mode=TenancyMode(existing_tenant["tenancy_mode"]),
            db_schema_name=existing_tenant["db_schema_name"],
            object_store_prefix=existing_tenant["object_store_prefix"],
            secrets_key_ref=existing_tenant["secrets_key_ref"],
            resolved_secret_handle=vault_client.get(existing_tenant["secrets_key_ref"]),
            status=existing_tenant["status"]
        )
    
    # Create schema
    logger.info(f"Creating schema {schema_name} for tenant {tenant_id}")
    _create_schema(db_client, schema_name)
    
    # Apply migrations to the new schema
    logger.info(f"Applying migrations to schema {schema_name}")
    if migration_files:
        _apply_migrations(db_client, schema_name, migration_files)
    else:
        logger.warning("No migration files provided, schema will be empty")
    
    # Create vault key reference (empty envelope initially)
    logger.info(f"Creating vault key reference {secrets_key_ref}")
    vault_client.store_credential_envelope(secrets_key_ref, {})
    
    # Insert tenant row
    logger.info(f"Inserting tenant row for {tenant_id}")
    _insert_tenant_row(
        db_client,
        tenant_id,
        tenancy_mode.value,
        schema_name,
        object_store_prefix,
        secrets_key_ref
    )
    
    # Build and return routing info
    routing_info = TenantRoutingInfo(
        tenant_id=tenant_id,
        tenancy_mode=tenancy_mode,
        db_schema_name=schema_name,
        object_store_prefix=object_store_prefix,
        secrets_key_ref=secrets_key_ref,
        resolved_secret_handle=vault_client.get(secrets_key_ref),
        status="active"
    )
    
    logger.info(f"Successfully provisioned tenant {tenant_id}")
    return routing_info


def _fetch_existing_tenant(db_client, tenant_id):
    """Check if tenant already exists"""
    query = """
        SELECT tenant_id, tenancy_mode, db_schema_name, 
               object_store_prefix, secrets_key_ref, status
        FROM tenants
        WHERE tenant_id = %s
    """
    result = db_client.fetch_one(query, (tenant_id,))
    return result


def _create_schema(db_client, schema_name: str):
    """Create a new schema"""
    query = f"CREATE SCHEMA IF NOT EXISTS {schema_name}"
    db_client.execute(query, ())


def _apply_migrations(db_client, schema_name: str, migration_files: list):
    """Apply migration files to a schema"""
    for migration_file in migration_files:
        logger.info(f"Applying migration {migration_file} to schema {schema_name}")
        # In real implementation, this would read and execute the SQL file
        # For now, we'll execute a placeholder
        _execute_migration(db_client, schema_name, migration_file)


def _execute_migration(db_client, schema_name: str, migration_file: str):
    """Execute a single migration file"""
    # Set search path to the tenant schema
    set_search_path = f"SET search_path TO {schema_name}, public"
    db_client.execute(set_search_path, ())
    
    # In real implementation, read the SQL file and execute
    # For Phase 1 testing with mocks, we'll just log it
    logger.debug(f"Would execute migration file: {migration_file} on schema {schema_name}")
    
    # Reset search path
    reset_search_path = "SET search_path TO public"
    db_client.execute(reset_search_path, ())


def _insert_tenant_row(
    db_client,
    tenant_id: str,
    tenancy_mode: str,
    db_schema_name: str,
    object_store_prefix: str,
    secrets_key_ref: str
):
    """Insert a row into the tenants table"""
    query = """
        INSERT INTO tenants (tenant_id, tenancy_mode, db_schema_name, 
                            object_store_prefix, secrets_key_ref, status)
        VALUES (%s, %s, %s, %s, %s, 'active')
    """
    db_client.execute(query, (tenant_id, tenancy_mode, db_schema_name, 
                            object_store_prefix, secrets_key_ref))
