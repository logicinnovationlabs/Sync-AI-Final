"""
Tenant Router - Block D Component (a)
Provides tenant metadata lookup and routing information resolution.
"""

from .tenant_router import TenantRouter, TenantRoutingInfo
from .models import Tenant, TenancyMode

__all__ = ["TenantRouter", "TenantRoutingInfo", "Tenant", "TenancyMode"]
