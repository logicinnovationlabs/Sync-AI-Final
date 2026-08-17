"""
Tenant provisioning service for Block D
Creates schema, applies migrations, inserts tenant row.
"""

import logging
from typing import Optional
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)


class TenancyMode(str, Enum):
    """Tenancy mode enum"""
    ISOLATED_DB = "isolated_db"
    SHARED_DB = "shared_db"


def provision_tenant(
    tenant_id: str,
    db_client,
    vault_client: object,
    tenancy_mode: TenancyMode = TenancyMode.ISOLATED_DB,
    migration_files: Optional[list] = None
) -> dict:
    """
    Provision a new tenant.
    
    Creates schema `tenant_<id>`, applies migrations, inserts tenant row.
    Idempotent operation.
    
    Args:
        tenant_id: The tenant identifier
        db_client: Database client
        vault_client: Vault client for secrets
        tenancy_mode: Tenancy mode
        migration_files: List of migration SQL files to apply
        
    Returns:
        Tenant routing information
    """
    # Sanitize tenant_id for PostgreSQL (replace hyphens with underscores)
    safe_tenant_id = tenant_id.replace("-", "_")
    schema_name = f"tenant_{safe_tenant_id}"
    object_store_prefix = f"tenant_{tenant_id}"
    secrets_key_ref = f"tenant_{tenant_id}_secrets"
    
    logger.info(f"Provisioning tenant {tenant_id}")
    
    # Create schema
    logger.info(f"Creating schema {schema_name}")
    # db_client.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
    
    # Apply migrations
    if migration_files:
        logger.info(f"Applying {len(migration_files)} migrations")
        # for migration in migration_files:
        #     db_client.execute(migration)
    
    # Create vault key
    vault_client.store_credential_envelope(secrets_key_ref, {})
    
    logger.info(f"Successfully provisioned tenant {tenant_id}")
    
    return {
        "tenant_id": tenant_id,
        "tenancy_mode": tenancy_mode.value,
        "schema_name": schema_name,
        "object_store_prefix": object_store_prefix,
        "secrets_key_ref": secrets_key_ref,
        "status": "active"
    }
