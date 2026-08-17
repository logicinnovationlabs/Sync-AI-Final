"""
Vault module for Block D: Storage substrate.

Provides secrets management via pgsodium or fallback table storage.
"""

from .vault_client import VaultClient, VaultBackend, PgsodiumVaultBackend, TableVaultBackend
from app.storage.vault_client import (
    MockVaultClient,
    PlatformSecretKeys,
    vault_client,
)

__all__ = [
    "VaultClient",
    "VaultBackend",
    "PgsodiumVaultBackend",
    "TableVaultBackend",
    "MockVaultClient",
    "PlatformSecretKeys",
    "vault_client",
]
