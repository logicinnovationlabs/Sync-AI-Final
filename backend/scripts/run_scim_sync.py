"""
Script to manually trigger a SCIM sync.

Usage: python scripts/run_scim_sync.py --tenant-id <tenant_id>
"""

import asyncio
import argparse
import sys
from pathlib import Path
import httpx
from typing import List, Dict, Any

# Add backend directory to Python path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.scim_sync import scim_sync_service
from app.storage.tenant_db import tenant_db_manager
from app.services.tenant_resolver import tenant_resolver
from app.core.config import settings


async def fetch_scim_users(endpoint: str, token: str) -> List[Dict[str, Any]]:
    """Fetch users from SCIM endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{endpoint}/Users",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("Resources", [])


async def fetch_scim_groups(endpoint: str, token: str) -> List[Dict[str, Any]]:
    """Fetch groups from SCIM endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{endpoint}/Groups",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("Resources", [])


async def run_scim_sync(tenant_id: str):
    """Run SCIM sync for a tenant."""
    print(f"Starting SCIM sync for tenant: {tenant_id}")
    
    if not settings.scim_endpoint or not settings.scim_token:
        print("ERROR: SCIM_ENDPOINT and SCIM_TOKEN must be configured")
        return
    
    # Resolve tenant
    routing = await tenant_resolver.resolve(tenant_id)
    print(f"✓ Resolved tenant: {routing.tenant_id}")
    
    # Fetch SCIM data
    print("Fetching users from SCIM endpoint...")
    users = await fetch_scim_users(settings.scim_endpoint, settings.scim_token)
    print(f"✓ Fetched {len(users)} users")
    
    print("Fetching groups from SCIM endpoint...")
    groups = await fetch_scim_groups(settings.scim_endpoint, settings.scim_token)
    print(f"✓ Fetched {len(groups)} groups")
    
    # Sync to tenant database
    async for db_session in tenant_db_manager.get_session(
        routing.db_host,
        routing.db_name,
        routing.db_user,
        routing.db_password,
        tenant_id,
    ):
        print("Syncing users...")
        user_stats = await scim_sync_service.sync_users(users, routing.tenant_id, db_session)
        print(f"✓ Users: {user_stats}")
        
        print("Syncing groups...")
        group_stats = await scim_sync_service.sync_groups(groups, routing.tenant_id, db_session)
        print(f"✓ Groups: {group_stats}")
    
    print("✓ SCIM sync complete")


def main():
    parser = argparse.ArgumentParser(description="Run SCIM sync for a tenant")
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID")
    args = parser.parse_args()
    
    asyncio.run(run_scim_sync(args.tenant_id))


if __name__ == "__main__":
    main()
