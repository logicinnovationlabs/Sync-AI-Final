"""
Vault client abstraction: secrets NEVER stored in the tenants table.

Per Vishwas §28.2/§28.6: the tenants table stores a Vault key NAME (pointer),
and the actual secret lives only in Vault, fetched at runtime.

Provides:
- VaultClient interface (abstract)
- AzureKeyVaultClient (real Azure Key Vault)
- MockVaultClient (env-var backed for dev/test, no real Vault needed)

The system auto-selects MockVaultClient if VAULT_URL is blank.
"""

from abc import ABC, abstractmethod
from typing import Optional
import os

from app.core.config import settings
from app.core.exceptions import VaultError


class VaultClient(ABC):
    """Abstract interface for secret storage."""

    @abstractmethod
    async def get_secret(self, key_name: str) -> str:
        """
        Retrieve a secret by key name.
        
        Args:
            key_name: Vault key name (e.g., 'kv/tenantA/db_password')
            
        Returns:
            Secret value as a string.
            
        Raises:
            VaultError if the secret cannot be retrieved.
        """
        ...

    @abstractmethod
    async def set_secret(self, key_name: str, secret_value: str) -> None:
        """
        Store a secret by key name.
        
        Args:
            key_name: Vault key name
            secret_value: Secret to store
            
        Raises:
            VaultError if the secret cannot be stored.
        """
        ...


class AzureKeyVaultClient(VaultClient):
    """
    Real Azure Key Vault client.
    
    Requires VAULT_URL, VAULT_TENANT_ID, VAULT_CLIENT_ID, VAULT_CLIENT_SECRET.
    """

    def __init__(
        self,
        vault_url: str,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ):
        from azure.identity import ClientSecretCredential
        from azure.keyvault.secrets import SecretClient

        self.vault_url = vault_url
        self.credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        self.client = SecretClient(vault_url=vault_url, credential=self.credential)

    async def get_secret(self, key_name: str) -> str:
        """
        Retrieve a secret from Azure Key Vault.
        
        Args:
            key_name: Secret name in Key Vault (e.g., 'tenant-a-db-password')
            
        Returns:
            Secret value.
            
        Raises:
            VaultError if retrieval fails.
        """
        try:
            # Azure Key Vault requires synchronous calls; wrap in executor for async
            import asyncio
            loop = asyncio.get_event_loop()
            secret = await loop.run_in_executor(None, self.client.get_secret, key_name)
            return secret.value
        except Exception as e:
            raise VaultError(f"Failed to get secret '{key_name}': {e}")

    async def set_secret(self, key_name: str, secret_value: str) -> None:
        """
        Store a secret in Azure Key Vault.
        
        Args:
            key_name: Secret name
            secret_value: Secret to store
            
        Raises:
            VaultError if storage fails.
        """
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.client.set_secret, key_name, secret_value)
        except Exception as e:
            raise VaultError(f"Failed to set secret '{key_name}': {e}")


class MockVaultClient(VaultClient):
    """
    Mock Vault client for dev/test (no real Vault required).
    
    Secrets are stored as environment variables:
    VAULT_SECRET_<key_name> = <secret_value>
    
    Example: VAULT_SECRET_kv_tenantA_db_password=mypassword
    """

    def __init__(self):
        self._in_memory_store = {}

    def _env_key(self, key_name: str) -> str:
        """Convert Vault key name to env var name."""
        # Replace slashes and hyphens with underscores for env var safety
        safe_name = key_name.replace("/", "_").replace("-", "_")
        return f"VAULT_SECRET_{safe_name}"

    async def get_secret(self, key_name: str) -> str:
        """
        Retrieve a secret from env vars or in-memory store.
        
        Args:
            key_name: Secret key name
            
        Returns:
            Secret value.
            
        Raises:
            VaultError if secret not found.
        """
        # Check in-memory store first (for runtime set_secret calls)
        if key_name in self._in_memory_store:
            return self._in_memory_store[key_name]
        
        # Check environment variable
        env_key = self._env_key(key_name)
        value = os.getenv(env_key)
        if value is None:
            # Fallback for dev/test mode
            if settings.environment in ("development", "test"):
                return "postgres"
            raise VaultError(
                f"Secret '{key_name}' not found. Set env var {env_key} or call set_secret()."
            )
        return value

    async def set_secret(self, key_name: str, secret_value: str) -> None:
        """
        Store a secret in the in-memory store.
        
        Args:
            key_name: Secret key name
            secret_value: Secret to store
        """
        self._in_memory_store[key_name] = secret_value
    
    def store_credential_envelope(self, key_ref: str, credentials: dict) -> None:
        """
        Store a credential envelope (sync method for compatibility).
        
        Args:
            key_ref: Secret key reference
            credentials: Credential data to store
        """
        # Store as JSON in the in-memory store
        import json
        self._in_memory_store[key_ref] = json.dumps(credentials)
    
    def set(self, key_name: str, value: str) -> None:
        """
        Sync method to store a secret (for compatibility with EncryptionClient).
        
        Args:
            key_name: Secret key name
            value: Secret value to store
        """
        self._in_memory_store[key_name] = value
    
    def get(self, key_name: str) -> str:
        """
        Sync method to retrieve a secret (for compatibility with EncryptionClient).
        
        Args:
            key_name: Secret key name
            
        Returns:
            Secret value
        """
        if key_name in self._in_memory_store:
            return self._in_memory_store[key_name]
        # Fallback for dev/test
        return "mock-secret"


def get_vault_client() -> VaultClient:
    """
    Factory function to get the appropriate VaultClient.
    
    Returns:
        AzureKeyVaultClient if VAULT_URL is set, otherwise MockVaultClient.
    """
    if settings.vault_url:
        # Real Azure Key Vault
        if not all([
            settings.vault_tenant_id,
            settings.vault_client_id,
            settings.vault_client_secret,
        ]):
            raise VaultError(
                "VAULT_URL is set but missing VAULT_TENANT_ID, VAULT_CLIENT_ID, or VAULT_CLIENT_SECRET"
            )
        return AzureKeyVaultClient(
            vault_url=settings.vault_url,
            tenant_id=settings.vault_tenant_id,
            client_id=settings.vault_client_id,
            client_secret=settings.vault_client_secret,
        )
    else:
        # Mock Vault for dev/test
        return MockVaultClient()


# Global vault client instance
vault_client = get_vault_client()
