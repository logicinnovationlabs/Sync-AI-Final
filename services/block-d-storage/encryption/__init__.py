"""
Encryption/KMS - Block D Component (f)
Envelope encryption for sensitive columns via pgsodium.
"""

from .encryption_client import EncryptionClient

__all__ = ["EncryptionClient"]
