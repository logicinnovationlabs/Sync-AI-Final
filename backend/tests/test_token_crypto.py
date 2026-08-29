"""Token encryption hardening: vault-only root, per-tenant keys, no passphrase hash."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.connectors import token_crypto
from app.connectors.token_crypto import (
    TokenEncryptionError,
    decrypt_token_blob,
    derive_tenant_fernet_key,
    encrypt_token_blob,
    load_root_fernet_key,
    require_valid_fernet_key,
    reset_root_fernet_key_cache,
)
from app.core.config import settings
from app.core.startup import StartupConfigurationError, validate_startup_config


def test_require_valid_fernet_key_rejects_passphrase():
    with pytest.raises(TokenEncryptionError, match="not a valid Fernet key"):
        require_valid_fernet_key("not-a-fernet-passphrase", source="TOKEN_ENCRYPTION_KEY")


def test_require_valid_fernet_key_accepts_fernet():
    key = Fernet.generate_key().decode()
    assert require_valid_fernet_key(key, source="TOKEN_ENCRYPTION_KEY") == key.encode()


def test_per_tenant_keys_differ(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "token_encryption_key", key)
    reset_root_fernet_key_cache()
    root = load_root_fernet_key(scrub_redis=False)
    a = derive_tenant_fernet_key("tenant-a", root)
    b = derive_tenant_fernet_key("tenant-b", root)
    assert a != b
    assert a != root


def test_legacy_global_blob_still_decrypts(monkeypatch):
    """Blobs encrypted with the old single global key remain readable once."""
    key = Fernet.generate_key()
    monkeypatch.setattr(settings, "token_encryption_key", key.decode())
    reset_root_fernet_key_cache()
    legacy_ct = Fernet(key).encrypt(b'{"access_token":"legacy"}').decode()
    plain = decrypt_token_blob(legacy_ct, tenant_id="tenant-migrate")
    assert "legacy" in plain


def test_root_key_never_written_to_redis(monkeypatch):
    writes = []

    class _FakeRedis:
        def get(self, name):
            return None

        def set(self, name, value):
            writes.append(("set", name))

        def delete(self, name):
            writes.append(("delete", name))
            return 1

        def ping(self):
            return True

    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    reset_root_fernet_key_cache()
    monkeypatch.setattr(
        "app.storage.redis_client.create_sync_redis_client",
        lambda *a, **k: _FakeRedis(),
    )
    load_root_fernet_key(scrub_redis=True)
    encrypt_token_blob('{"a":1}', tenant_id="t1")
    # May delete the legacy key name; must never SET the plaintext root key into Redis.
    assert ("set", token_crypto._LEGACY_REDIS_FERNET_KEY) not in writes
    assert ("delete", token_crypto._LEGACY_REDIS_FERNET_KEY) in writes


def test_startup_rejects_invalid_token_encryption_key(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "token_encryption_key", "low-entropy-passphrase")
    with pytest.raises(StartupConfigurationError, match="Fernet"):
        validate_startup_config()


def test_startup_requires_redis_password_outside_dev(monkeypatch, tmp_path):
    priv = tmp_path / "private.pem"
    pub = tmp_path / "public.pem"
    # Minimal PEM placeholders so JWT path checks pass as files.
    priv.write_text("x")
    pub.write_text("x")
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_private_key_path", str(priv))
    monkeypatch.setattr(settings, "jwt_public_key_path", str(pub))
    monkeypatch.setattr(settings, "vault_url", "https://vault.example")
    monkeypatch.setattr(settings, "session_store_redis_url", "redis://localhost:6379/0")
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "storage_backend", "minio")
    monkeypatch.setattr(settings, "graph_backend", "neo4j")
    monkeypatch.setattr(settings, "signals_backend", "postgres")
    monkeypatch.setattr(settings, "vault_backend", "azure")
    monkeypatch.setattr(settings, "acl_backend", "postgres")
    with pytest.raises(StartupConfigurationError, match="password"):
        validate_startup_config()
