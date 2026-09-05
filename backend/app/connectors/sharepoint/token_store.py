"""Persistent SharePoint OAuth token store (Vault + Redis, matching Google)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.core.base_connector import TokenStore
from app.storage.vault_client import vault_client
from app.connectors.sharepoint.keys import (
    vault_sharepoint_oauth_key,
)

logger = logging.getLogger(__name__)

_REDIS_PREFIX = "sharepoint_oauth_blob"
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
    except Exception:
        _REDIS = None
        return None


def _redis_blob_key(tenant_id: str, token_key: str) -> str:
    return f"{_REDIS_PREFIX}:{tenant_id}:{token_key}"


def _uid_and_scope_from_token_key(key: str) -> tuple[str, str]:
    parts = (key or "").split(":")
    uid = parts[2] if len(parts) > 2 else ""
    scope = parts[3] if len(parts) > 3 else "personal"
    return uid, scope


class PersistentSharePointTokenStore(TokenStore):
    def __init__(self, tenant_id: str):
        self.tenant_id = str(tenant_id)

    def get_token(self, key: str) -> Optional[Dict[str, Any]]:
        redis_client = _sync_redis()
        if redis_client is not None:
            try:
                raw = redis_client.get(_redis_blob_key(self.tenant_id, key))
                if raw:
                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode("utf-8")
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return data
            except Exception:
                logger.warning("SharePoint token Redis read failed tenant=%s", self.tenant_id)

        data = self._read_vault(key)
        if data and redis_client is not None:
            try:
                redis_client.set(_redis_blob_key(self.tenant_id, key), json.dumps(data))
            except Exception:
                logger.warning("SharePoint token Redis backfill failed tenant=%s", self.tenant_id)
        return data

    def set_token(self, key: str, token_data: Dict[str, Any]) -> None:
        blob = json.dumps(token_data)
        redis_client = _sync_redis()
        if redis_client is not None:
            try:
                redis_client.set(_redis_blob_key(self.tenant_id, key), blob)
            except Exception:
                logger.warning("SharePoint token Redis write failed tenant=%s", self.tenant_id)
        # Vault write is synchronous and awaited (Google-style vault_client.set).
        # The previous create_task() path was dropped on process restart, which
        # is why Redis+Vault were both empty after an app bounce mid-session.
        try:
            self._write_vault(key, blob)
        except Exception:
            logger.warning("SharePoint token Vault write failed tenant=%s", self.tenant_id)

    def _vault_key(self, token_key: str) -> str:
        uid, scope = _uid_and_scope_from_token_key(token_key)
        return vault_sharepoint_oauth_key(self.tenant_id, uid, scope)

    def _read_vault(self, token_key: str) -> Optional[Dict[str, Any]]:
        vault_key = self._vault_key(token_key)
        try:
            if not hasattr(vault_client, "get"):
                return None
            raw = vault_client.get(vault_key)
            if raw in (None, "", "mock-secret"):
                return None
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _write_vault(self, token_key: str, blob: str) -> None:
        vault_key = self._vault_key(token_key)
        if not hasattr(vault_client, "set"):
            raise RuntimeError("vault_client.set is required for durable SharePoint tokens")
        vault_client.set(vault_key, blob)


def sharepoint_credential_ref(tenant_id: str, user_id: str, connection_scope: str) -> str:
    return vault_sharepoint_oauth_key(tenant_id, user_id, connection_scope)
