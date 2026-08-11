"""
Encryption module for Block D: Storage substrate.

Provides envelope encryption using pgcrypto for sensitive columns.
"""

from .encryption_client import EncryptionClient

__all__ = ["EncryptionClient"]
