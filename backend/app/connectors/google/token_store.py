"""
Persistent, vault-referenced Google OAuth token store.

EncryptionClient.encrypt() (pgcrypto envelope) is not used here: it requires a
synchronous pgcrypto db_client that is not wired into the FastAPI/Celery path.
The vault-backed key-reference discipline from EncryptionClient / §15.2 is
reused: a Fernet key lives in Vault under a key *name*; only ciphertext is
stored. Redis holds the same ciphertext so MockVaultClient (process-local)
cannot strand Celery workers after the API process stores tokens.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.base_connector import TokenStore
from app.core.config import settings
from app.storage.vault_client import vault_client
from app.connectors.google.keys import (
    principal_from_token_key,
    tenant_from_token_key,
    vault_google_oauth_key,
)

logger = logging.getLogger(__name__)

_FERNET_VAULT_KEY = "kv/platform/google-oauth-fernet"
_REDIS_PREFIX = "google_oauth_blob"


def _redis_blob_key(tenant_id: str, token_key: str) -> str:
    return f"{_REDIS_PREFIX}:{tenant_id}:{token_key}"


_REDIS = None
_REDIS_INIT = False


def _sync_redis():
    global _REDIS, _REDIS_INIT
    if _REDIS_INIT:
        return _REDIS
    _REDIS_INIT = True
    try:
        import redis

        url = getattr(settings, "redis_url", None) or settings.session_store_redis_url
        client = redis.Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=0.2, socket_timeout=0.2
        )
        client.ping()
        _REDIS = client
        return _REDIS
    except Exception as exc:
        logger.warning("Google token store: Redis unavailable (%s); vault-only", type(exc).__name__)
        _REDIS = None
        return None


def _ensure_fernet_key() -> bytes:
    """
    Return a Fernet key, stored in Vault by name (and Redis for cross-process).

    Local bootstrap: if TOKEN_ENCRYPTION_KEY is set, that value is used (and
    stored in vault). Otherwise a generated key is persisted in Redis+vault so
    the API process and Celery workers share it.
    """
    redis_client = _sync_redis()
    redis_key_name = "kv_platform_google_oauth_fernet"

    bootstrap = (settings.token_encryption_key or "").strip()
    if bootstrap:
        key_bytes = bootstrap.encode("utf-8")
        try:
            Fernet(key_bytes)
        except Exception:
            import hashlib
            import base64

            key_bytes = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
        _persist_fernet_key(key_bytes, redis_client, redis_key_name)
        return key_bytes if isinstance(key_bytes, bytes) else key_bytes.encode("utf-8")

    existing = None
    if redis_client is not None:
        try:
            existing = redis_client.get(redis_key_name)
        except Exception:
            existing = None
    if not existing:
        try:
            if hasattr(vault_client, "get"):
                existing = vault_client.get(_FERNET_VAULT_KEY)
                if existing in (None, "", "mock-secret"):
                    existing = None
        except Exception:
            existing = None

    if existing:
        return existing.encode("utf-8") if isinstance(existing, str) else existing

    key_bytes = Fernet.generate_key()
    _persist_fernet_key(key_bytes, redis_client, redis_key_name)
    return key_bytes


def _persist_fernet_key(key_bytes: bytes, redis_client, redis_key_name: str) -> None:
    key_str = key_bytes.decode("utf-8") if isinstance(key_bytes, bytes) else key_bytes
    if redis_client is not None:
        try:
            redis_client.set(redis_key_name, key_str)
        except Exception:
            pass
    try:
        if hasattr(vault_client, "set"):
            vault_client.set(_FERNET_VAULT_KEY, key_str)
    except Exception as exc:
        logger.warning("Could not persist Fernet key in vault: %s", type(exc).__name__)


def encrypt_token_blob(plaintext_json: str) -> str:
    """Encrypt a JSON token blob. Return ciphertext string. Never logs plaintext."""
    fernet = Fernet(_ensure_fernet_key())
    return fernet.encrypt(plaintext_json.encode("utf-8")).decode("utf-8")


def decrypt_token_blob(ciphertext: str) -> str:
    """Decrypt a token blob ciphertext. Return plaintext JSON. Never logs it."""
    fernet = Fernet(_ensure_fernet_key())
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


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
            vault_name = vault_google_oauth_key(tenant_id, principal_from_token_key(key))
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
            plaintext = decrypt_token_blob(ciphertext)
            data = json.loads(plaintext)
        except Exception as exc:
            logger.error("Failed to decrypt Google OAuth token blob: %s", type(exc).__name__)
            return None

        self._memory[key] = data
        return data

    def set_token(self, key: str, token_data: Dict[str, Any]) -> None:
        self._memory[key] = token_data
        tenant_id = self.tenant_id or tenant_from_token_key(key)
        try:
            ciphertext = encrypt_token_blob(json.dumps(token_data))
        except Exception as exc:
            logger.error("Failed to encrypt Google OAuth token blob: %s", type(exc).__name__)
            return

        if self._redis is not None and tenant_id:
            try:
                self._redis.set(_redis_blob_key(tenant_id, key), ciphertext)
            except Exception as exc:
                logger.warning("Redis token persist failed: %s", type(exc).__name__)

        if tenant_id:
            vault_name = vault_google_oauth_key(tenant_id, principal_from_token_key(key))
            try:
                if hasattr(vault_client, "set"):
                    vault_client.set(vault_name, ciphertext)
            except Exception as exc:
                logger.warning("Vault token persist failed: %s", type(exc).__name__)


def google_credential_ref(tenant_id: str, user_id: str = "") -> str:
    """Vault key *name* stored on TenantConnector.credential_ref — never a secret."""
    return vault_google_oauth_key(tenant_id, user_id)
