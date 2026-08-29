"""Production startup validation — fail closed before serving traffic."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from app.core.backends import mock_backends_allowed, refuse_mock_backend
from app.core.config import settings

logger = logging.getLogger(__name__)


class StartupConfigurationError(RuntimeError):
    """Raised when mandatory production configuration is missing or unsafe."""


def _redis_url_has_password(url: str) -> bool:
    """True when the Redis URL embeds a password (redis://:pass@host or user:pass@host)."""
    cleaned = (url or "").strip().strip('"').strip("'")
    if not cleaned:
        return False
    parsed = urlparse(cleaned)
    return bool(parsed.password)


def validate_startup_config() -> None:
    """
    Validate configuration at boot.

    In development/test, missing JWT keys may be auto-generated. In production
    and staging, misconfiguration aborts startup immediately.
    """
    env = (settings.environment or "development").strip().lower()
    is_relaxed = mock_backends_allowed()

    private_path = Path(settings.jwt_private_key_path)
    public_path = Path(settings.jwt_public_key_path)
    if not is_relaxed:
        if not private_path.is_file():
            raise StartupConfigurationError(
                f"JWT private key missing at {private_path}; "
                "refusing to boot with ephemeral keys in production"
            )
        if not public_path.is_file():
            raise StartupConfigurationError(
                f"JWT public key missing at {public_path}; "
                "refusing to boot without verification keys in production"
            )
        if not settings.vault_url:
            raise StartupConfigurationError(
                "VAULT_URL is required outside development/test; "
                "MockVaultClient must not be used in production"
            )

        redis_url = (
            getattr(settings, "redis_url", None)
            or settings.session_store_redis_url
            or ""
        )
        if not _redis_url_has_password(str(redis_url)):
            raise StartupConfigurationError(
                "REDIS_URL / SESSION_STORE_REDIS_URL must include a password "
                "outside development/test (e.g. redis://:SECRET@host:6379/0). "
                "Unauthenticated Redis must not hold connector ciphertext."
            )
        for label, broker in (
            ("CELERY_BROKER_URL", getattr(settings, "celery_broker_url", None)),
            ("CELERY_RESULT_BACKEND", getattr(settings, "celery_result_backend", None)),
        ):
            if broker and str(broker).startswith("redis") and not _redis_url_has_password(
                str(broker)
            ):
                raise StartupConfigurationError(
                    f"{label} must include Redis credentials outside development/test"
                )

    token_key = (settings.token_encryption_key or "").strip()
    if token_key:
        from app.connectors.token_crypto import (
            TokenEncryptionError,
            require_valid_fernet_key,
        )

        try:
            require_valid_fernet_key(token_key, source="TOKEN_ENCRYPTION_KEY")
        except TokenEncryptionError as exc:
            raise StartupConfigurationError(str(exc)) from exc

    refuse_mock_backend("STORAGE_BACKEND", settings.storage_backend, "minio")
    refuse_mock_backend("GRAPH_BACKEND", settings.graph_backend, "neo4j")
    refuse_mock_backend("SIGNALS_BACKEND", settings.signals_backend, "postgres")
    refuse_mock_backend("VAULT_BACKEND", settings.vault_backend, "azure")

    if not is_relaxed and (settings.acl_backend or "mock").strip().lower() == "mock":
        raise StartupConfigurationError(
            "ACL_BACKEND=mock is not allowed outside development/test"
        )

    logger.info("Startup configuration validated (environment=%s)", env)
