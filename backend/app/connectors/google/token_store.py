"""
Persistent, vault-referenced Google OAuth token store.

EncryptionClient.encrypt() (pgcrypto envelope) is not used here: it requires a
synchronous pgcrypto db_client that is not wired into the FastAPI/Celery path.

Vault-backed key-reference discipline (§15.2):
- The Fernet *root* key lives only in Vault (or TOKEN_ENCRYPTION_KEY at boot).
- Per-tenant Fernet keys are HKDF-derived from that root.
- Only ciphertext is stored in Redis / Vault — never the encryption key.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.connectors.google.keys import (
    principal_from_token_key,
    scope_from_token_key,
    tenant_from_token_key,
    vault_google_oauth_key,
)
from app.connectors.token_crypto import decrypt_token_blob, encrypt_token_blob
from app.core.base_connector import TokenStore
from app.storage.vault_client import vault_client

logger = logging.getLogger(__name__)

_REDIS_PREFIX = "google_oauth_blob"

_REDIS = None
_REDIS_INIT = False


def _redis_blob_key(tenant_id: str, token_key: str) -> str:
    return f"{_REDIS_PREFIX}:{tenant_id}:{token_key}"


def _sync_redis():
    global _REDIS, _REDIS_INIT
    if _REDIS_INIT:
        return _REDIS
    _REDIS_INIT = True
    try:
        from app.storage.redis_client import create_sync_redis_client

        _REDIS = create_sync_redis_client()
        return _REDIS
    except Exception as exc:
        logger.warning(
            "Google token store: Redis unavailable (%s); vault-only",
            type(exc).__name__,
        )
        _REDIS = None
        return None


# Re-export for tests / callers that imported from this module.
__all__ = [
    "PersistentGoogleTokenStore",
    "encrypt_token_blob",
    "decrypt_token_blob",
    "google_credential_ref",
]


class PersistentGoogleTokenStore(TokenStore):
    """TokenStore that encrypts blobs and persists them in Vault + Redis."""

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._redis = _sync_redis()

    def bind_tenant(self, tenant_id: str) -> "PersistentGoogleTokenStore":
        self.tenant_id = tenant_id
        return self

    def get_token(self, key: str) -> Optional[Dict[str, Any]]:
        if key in self._memory:
            return self._memory[key]

        tenant_id = self.tenant_id or tenant_from_token_key(key)
        ciphertext = None

        if self._redis is not None and tenant_id:
            try:
                ciphertext = self._redis.get(_redis_blob_key(tenant_id, key))
            except Exception:
                ciphertext = None

        if not ciphertext and tenant_id:
            vault_name = vault_google_oauth_key(
                tenant_id, principal_from_token_key(key), scope_from_token_key(key)
            )
            try:
                if hasattr(vault_client, "get"):
                    ciphertext = vault_client.get(vault_name)
                    if ciphertext in (None, "", "mock-secret"):
                        ciphertext = None
            except Exception:
                ciphertext = None

        if not ciphertext:
            return None

        try:
            plaintext = decrypt_token_blob(ciphertext, tenant_id=str(tenant_id))
            data = json.loads(plaintext)
        except Exception as exc:
            logger.error(
                "Failed to decrypt Google OAuth token blob: %s", type(exc).__name__
            )
            return None

        self._memory[key] = data
        return data

    def set_token(self, key: str, token_data: Dict[str, Any]) -> None:
        self._memory[key] = token_data
        tenant_id = self.tenant_id or tenant_from_token_key(key)
        if not tenant_id:
            logger.error("Cannot encrypt Google OAuth token blob without tenant_id")
            return
        try:
            ciphertext = encrypt_token_blob(
                json.dumps(token_data), tenant_id=str(tenant_id)
            )
        except Exception as exc:
            logger.error(
                "Failed to encrypt Google OAuth token blob: %s", type(exc).__name__
            )
            return

        if self._redis is not None:
            try:
                self._redis.set(_redis_blob_key(tenant_id, key), ciphertext)
            except Exception as exc:
                logger.warning("Redis token persist failed: %s", type(exc).__name__)

        vault_name = vault_google_oauth_key(
            tenant_id, principal_from_token_key(key), scope_from_token_key(key)
        )
        try:
            if hasattr(vault_client, "set"):
                vault_client.set(vault_name, ciphertext)
        except Exception as exc:
            logger.warning("Vault token persist failed: %s", type(exc).__name__)

    def clear_token(self, key: str) -> None:
        """Remove OAuth blob from memory, Redis, and Vault."""
        self._memory.pop(key, None)
        tenant_id = self.tenant_id or tenant_from_token_key(key)
        if self._redis is not None and tenant_id:
            try:
                self._redis.delete(_redis_blob_key(tenant_id, key))
            except Exception:
                pass
        if tenant_id:
            vault_name = vault_google_oauth_key(
                tenant_id, principal_from_token_key(key), scope_from_token_key(key)
            )
            try:
                if hasattr(vault_client, "delete"):
                    vault_client.delete(vault_name)
            except Exception:
                pass


def google_credential_ref(
    tenant_id: str, user_id: str = "", connection_scope: str = "personal"
) -> str:
    """Vault key *name* stored on TenantConnector.credential_ref — never a secret."""
    return vault_google_oauth_key(tenant_id, user_id, connection_scope)
