"""OAuth token blob encryption — vault-held root key, per-tenant Fernet keys.

Security model:
- The root Fernet key lives in Vault (or ``TOKEN_ENCRYPTION_KEY`` at boot).
- It is NEVER written to Redis next to ciphertext.
- Per-tenant keys are HKDF-derived from the root so one tenant breach is not total.
- ``TOKEN_ENCRYPTION_KEY`` must already be a valid Fernet key — we do not hash
  passphrases into keys (unsalted SHA-256 was previously used; that is rejected).
"""

from __future__ import annotations

import base64
import logging
import threading
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings
from app.storage.vault_client import vault_client

logger = logging.getLogger(__name__)

# Vault key *name* for the platform root OAuth encryption key (never a Redis key).
FERNET_ROOT_VAULT_KEY = "kv/platform/google-oauth-fernet"
# Legacy Redis key that previously stored the plaintext Fernet key — scrub on load.
_LEGACY_REDIS_FERNET_KEY = "kv_platform_google_oauth_fernet"
_HKDF_SALT = b"snyq-oauth-token-fernet-v1"
_HKDF_INFO_PREFIX = b"oauth-token-tenant:"

_root_key_lock = threading.Lock()
_root_key_cache: Optional[bytes] = None


class TokenEncryptionError(RuntimeError):
    """Raised when token encryption cannot be configured safely."""


def _scrub_legacy_redis_fernet_key() -> None:
    """Remove any plaintext Fernet key previously mirrored into Redis."""
    try:
        from app.storage.redis_client import create_sync_redis_client

        client = create_sync_redis_client()
        deleted = client.delete(_LEGACY_REDIS_FERNET_KEY)
        if deleted:
            logger.warning(
                "Removed legacy plaintext Fernet key from Redis (%s)",
                _LEGACY_REDIS_FERNET_KEY,
            )
    except Exception:
        # Redis may be down during unit tests; scrub is best-effort.
        pass


def require_valid_fernet_key(value: str, *, source: str) -> bytes:
    """Return key bytes if ``value`` is a real Fernet key; otherwise raise.

    Deliberately does **not** derive a key via ``sha256(passphrase)``.
    """
    text = (value or "").strip()
    if not text:
        raise TokenEncryptionError(f"{source} is empty")
    key_bytes = text.encode("utf-8")
    try:
        Fernet(key_bytes)
    except Exception as exc:
        raise TokenEncryptionError(
            f"{source} is not a valid Fernet key. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" '
            "and set TOKEN_ENCRYPTION_KEY (or store it in Vault). "
            "Passphrases are not accepted."
        ) from exc
    return key_bytes


def _vault_get_root() -> Optional[bytes]:
    try:
        if not hasattr(vault_client, "get"):
            return None
        existing = vault_client.get(FERNET_ROOT_VAULT_KEY)
        if existing in (None, "", "mock-secret"):
            return None
        return require_valid_fernet_key(
            existing if isinstance(existing, str) else existing.decode("utf-8"),
            source=f"Vault:{FERNET_ROOT_VAULT_KEY}",
        )
    except TokenEncryptionError:
        raise
    except Exception:
        return None


def _vault_set_root(key_bytes: bytes) -> None:
    key_str = key_bytes.decode("utf-8")
    try:
        if hasattr(vault_client, "set"):
            vault_client.set(FERNET_ROOT_VAULT_KEY, key_str)
            return
    except Exception as exc:
        logger.warning(
            "Could not persist OAuth Fernet root in Vault: %s", type(exc).__name__
        )
        raise TokenEncryptionError(
            "Failed to persist OAuth encryption root key in Vault; "
            "refusing to keep the key only in process memory or Redis."
        ) from exc
    raise TokenEncryptionError("Vault client cannot store secrets (missing set())")


def load_root_fernet_key(*, scrub_redis: bool = True) -> bytes:
    """Load the platform root Fernet key from env or Vault — never from Redis."""
    global _root_key_cache
    with _root_key_lock:
        if _root_key_cache is not None:
            return _root_key_cache

        if scrub_redis:
            _scrub_legacy_redis_fernet_key()

        bootstrap = (settings.token_encryption_key or "").strip()
        if bootstrap:
            key_bytes = require_valid_fernet_key(
                bootstrap, source="TOKEN_ENCRYPTION_KEY"
            )
            # Keep Vault in sync so workers with Vault access share the same root
            # without reading Redis. Best-effort: env already supplies the key.
            try:
                _vault_set_root(key_bytes)
            except TokenEncryptionError:
                logger.info(
                    "TOKEN_ENCRYPTION_KEY accepted; Vault persist skipped or failed "
                    "(workers must use the same env key or a shared Vault)."
                )
            _root_key_cache = key_bytes
            return key_bytes

        existing = _vault_get_root()
        if existing:
            _root_key_cache = existing
            return existing

        # No env key and no Vault material — generate once and Vault-only persist.
        key_bytes = Fernet.generate_key()
        _vault_set_root(key_bytes)
        _root_key_cache = key_bytes
        logger.info(
            "Generated new OAuth Fernet root key and stored it in Vault only "
            "(%s). Set TOKEN_ENCRYPTION_KEY to the same value on all workers "
            "if Vault is process-local (MockVault).",
            FERNET_ROOT_VAULT_KEY,
        )
        return key_bytes


def reset_root_fernet_key_cache() -> None:
    """Test helper — clear the process-local root key cache."""
    global _root_key_cache
    with _root_key_lock:
        _root_key_cache = None


def derive_tenant_fernet_key(tenant_id: str, root_key: Optional[bytes] = None) -> bytes:
    """HKDF-derive a per-tenant Fernet key from the platform root key."""
    tid = (tenant_id or "").strip()
    if not tid:
        raise TokenEncryptionError("tenant_id is required to derive a token encryption key")
    root = root_key if root_key is not None else load_root_fernet_key()
    # Fernet keys are urlsafe-base64(32 raw bytes).
    raw_root = base64.urlsafe_b64decode(root)
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO_PREFIX + tid.encode("utf-8"),
    ).derive(raw_root)
    return base64.urlsafe_b64encode(derived)


def _fernet_for_tenant(tenant_id: str) -> Fernet:
    return Fernet(derive_tenant_fernet_key(tenant_id))


def encrypt_token_blob(plaintext_json: str, *, tenant_id: str) -> str:
    """Encrypt a JSON token blob with the tenant-derived Fernet key."""
    fernet = _fernet_for_tenant(tenant_id)
    return fernet.encrypt(plaintext_json.encode("utf-8")).decode("utf-8")


def decrypt_token_blob(ciphertext: str, *, tenant_id: str) -> str:
    """Decrypt a token blob. Tries tenant key first, then legacy global root key."""
    try:
        return _fernet_for_tenant(tenant_id).decrypt(ciphertext.encode("utf-8")).decode(
            "utf-8"
        )
    except InvalidToken:
        # Legacy blobs encrypted with the single global root key (pre per-tenant HKDF).
        try:
            legacy = Fernet(load_root_fernet_key()).decrypt(
                ciphertext.encode("utf-8")
            ).decode("utf-8")
            logger.info(
                "Decrypted legacy global-key OAuth blob for tenant=%s; "
                "re-encrypt on next token refresh",
                tenant_id,
            )
            return legacy
        except InvalidToken:
            raise
