"""Persistent Microsoft OAuth token store (Fernet + Redis/Vault)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.connectors.microsoft.keys import (
    microsoft_oauth_token_key,
    principal_from_token_key,
    tenant_from_token_key,
    vault_microsoft_oauth_key,
)
from app.connectors.token_crypto import decrypt_token_blob, encrypt_token_blob
from app.core.base_connector import TokenStore
from app.storage.vault_client import vault_client

logger = logging.getLogger(__name__)

_REDIS_PREFIX = "microsoft_oauth_blob"
_REDIS = None
_REDIS_INIT = False


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
        logger.warning("Microsoft token store: Redis unavailable (%s)", type(exc).__name__)
        _REDIS = None
        return None


def _redis_blob_key(tenant_id: str, token_key: str) -> str:
    return f"{_REDIS_PREFIX}:{tenant_id}:{token_key}"


class PersistentMicrosoftTokenStore(TokenStore):
    """Encrypts Microsoft OAuth blobs and persists them in Vault + Redis."""

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._redis = _sync_redis()

    def bind_tenant(self, tenant_id: str) -> "PersistentMicrosoftTokenStore":
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
            vault_name = vault_microsoft_oauth_key(tenant_id, principal_from_token_key(key))
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
            logger.error("Failed to decrypt Microsoft OAuth token blob: %s", type(exc).__name__)
            return None

        self._memory[key] = data
        return data

    def set_token(self, key: str, token_data: Dict[str, Any]) -> None:
        self._memory[key] = token_data
        tenant_id = self.tenant_id or tenant_from_token_key(key)
        if not tenant_id:
            logger.error("Cannot encrypt Microsoft OAuth token blob without tenant_id")
            return
        try:
            ciphertext = encrypt_token_blob(
                json.dumps(token_data), tenant_id=str(tenant_id)
            )
        except Exception as exc:
            logger.error("Failed to encrypt Microsoft OAuth token blob: %s", type(exc).__name__)
            return

        if self._redis is not None and tenant_id:
            try:
                self._redis.set(_redis_blob_key(tenant_id, key), ciphertext)
            except Exception as exc:
                logger.warning("Redis MS token persist failed: %s", type(exc).__name__)

        if tenant_id:
            vault_name = vault_microsoft_oauth_key(tenant_id, principal_from_token_key(key))
            try:
                if hasattr(vault_client, "set"):
                    vault_client.set(vault_name, ciphertext)
            except Exception as exc:
                logger.warning("Vault MS token persist failed: %s", type(exc).__name__)

    def clear_token(self, key: str) -> None:
        self._memory.pop(key, None)
        tenant_id = self.tenant_id or tenant_from_token_key(key)
        if self._redis is not None and tenant_id:
            try:
                self._redis.delete(_redis_blob_key(tenant_id, key))
            except Exception:
                pass
        if tenant_id:
            vault_name = vault_microsoft_oauth_key(tenant_id, principal_from_token_key(key))
            try:
                if hasattr(vault_client, "delete"):
                    vault_client.delete(vault_name)
            except Exception:
                pass


def microsoft_credential_ref(tenant_id: str, user_id: str = "") -> str:
    return vault_microsoft_oauth_key(tenant_id, user_id)
