"""Seed a fake SharePoint Graph app credential for dev testing.

This writes an obviously fake client-credentials JSON into MockVault so the
Admin "Connect Service Account" flow can be exercised without an Azure app.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.storage.vault_client import vault_client
from app.connectors.sharepoint.credentials import cache_app_secret, DEV_FIXTURE_APP_SECRET, DEV_FIXTURE_VAULT_KEY

FAKE_SHAREPOINT_APP = DEV_FIXTURE_APP_SECRET
VAULT_KEY = DEV_FIXTURE_VAULT_KEY


async def main() -> int:
    print(f"Writing fake SharePoint app credentials to vault key: {VAULT_KEY}")
    print("WARNING: This is a DEV FIXTURE - NOT A REAL CREDENTIAL")
    await vault_client.set_secret(VAULT_KEY, json.dumps(FAKE_SHAREPOINT_APP))
    retrieved = await vault_client.get_secret(VAULT_KEY)
    parsed = json.loads(retrieved)
    cache_app_secret("dev-fixture", parsed)
    print("Successfully wrote and verified fake credential")
    print(f"  Vault key: {VAULT_KEY}")
    print(f"  Azure tenant id: {parsed['azure_tenant_id']}")
    print(f"  Client id: {parsed['client_id']}")
    print(f"  Has client_secret: {bool(parsed.get('client_secret'))}")
    print(f"  dev_fixture: {parsed.get('dev_fixture')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
