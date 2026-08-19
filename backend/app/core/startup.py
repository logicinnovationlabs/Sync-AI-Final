"""Production startup validation — fail closed before serving traffic."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.backends import mock_backends_allowed, refuse_mock_backend
from app.core.config import settings

logger = logging.getLogger(__name__)


class StartupConfigurationError(RuntimeError):
    """Raised when mandatory production configuration is missing or unsafe."""


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

    refuse_mock_backend("STORAGE_BACKEND", settings.storage_backend, "minio")
    refuse_mock_backend("GRAPH_BACKEND", settings.graph_backend, "neo4j")
    refuse_mock_backend("SIGNALS_BACKEND", settings.signals_backend, "postgres")
    refuse_mock_backend("VAULT_BACKEND", settings.vault_backend, "azure")

    if not is_relaxed and (settings.acl_backend or "mock").strip().lower() == "mock":
        raise StartupConfigurationError(
            "ACL_BACKEND=mock is not allowed outside development/test"
        )

    logger.info("Startup configuration validated (environment=%s)", env)
