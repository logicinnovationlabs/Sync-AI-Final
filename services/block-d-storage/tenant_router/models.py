"""
Data models for Tenant Router.
"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class TenancyMode(str, Enum):
    """Tenancy mode per Glean Arch v1.3 §6.1"""
    POOLED = "pooled"  # Not implemented in this block
    ISOLATED_DB = "isolated_db"  # Default: one schema per tenant
    DEDICATED = "dedicated"  # Stubbed only: separate DB instance per tenant


@dataclass
class Tenant:
    """Tenant row from the tenants table"""
    tenant_id: str
    tenancy_mode: TenancyMode
    db_schema_name: str
    object_store_prefix: str
    secrets_key_ref: str
    created_at: datetime
    status: str


@dataclass
class TenantRoutingInfo:
    """
    Resolved routing information for a tenant.
    Returned by TenantRouter.resolve(tenant_id).
    """
    tenant_id: str
    tenancy_mode: TenancyMode
    db_schema_name: str
    object_store_prefix: str
    secrets_key_ref: str
    resolved_secret_handle: Optional[str]  # Resolved from vault client
    status: str
