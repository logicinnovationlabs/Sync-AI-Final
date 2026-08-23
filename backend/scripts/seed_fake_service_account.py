"""Seed a fake Google Workspace service account credential for dev testing.

This creates an obviously fake service account JSON in the MockVaultClient
so the Organization connector Connect/Enable flow can be exercised without
needing real Google credentials.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.storage.vault_client import vault_client

# DEV FIXTURE - NOT A REAL CREDENTIAL
# This is obviously fake and cannot authenticate against real Google infrastructure
FAKE_SERVICE_ACCOUNT = {
    "type": "service_account",
    "project_id": "dev-fake-project-id",
    "private_key_id": "dev-fake-key-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\nDEV_FAKE_PRIVATE_KEY_NOT_REAL\nDO_NOT_USE_IN_PRODUCTION\n-----END PRIVATE KEY-----\n",
    "client_email": "dev-fake-service-account@example.invalid",
    "client_id": "dev-fake-client-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/dev-fake-service-account%40example.invalid",
    "# DEV_FIXTURE": "NOT_A_REAL_CREDENTIAL - DO_NOT_USE_IN_PRODUCTION"
}

VAULT_KEY = "kv/tenant/dev-fake-google-service-account"


async def main():
    print(f"Writing fake service account to vault key: {VAULT_KEY}")
    print("WARNING: This is a DEV FIXTURE - NOT A REAL CREDENTIAL")
    
    # Write the fake credential as JSON string
    await vault_client.set_secret(VAULT_KEY, json.dumps(FAKE_SERVICE_ACCOUNT))
    
    # Verify it can be read back
    retrieved = await vault_client.get_secret(VAULT_KEY)
    parsed = json.loads(retrieved)
    
    print(f"Successfully wrote and verified fake credential")
    print(f"  Vault key: {VAULT_KEY}")
    print(f"  Project ID: {parsed['project_id']}")
    print(f"  Client email: {parsed['client_email']}")
    print(f"  Has private_key: {bool(parsed.get('private_key'))}")
    print(f"  Has DEV_FIXTURE marker: {'# DEV_FIXTURE' in parsed}")
    
    return 0


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
