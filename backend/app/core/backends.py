"""Fail-closed mock-backend policy.

Mock stores (graph, signals, object storage, vault, ACL) are only allowed in
local development and automated tests. Production/staging must use real
backends so ACL, tenancy, and persistence cannot be silently skipped.
"""

from __future__ import annotations

from app.core.config import settings

_DEV_ENVIRONMENTS = frozenset({"development", "dev", "test"})


def mock_backends_allowed() -> bool:
    env = (settings.environment or "development").strip().lower()
    return env in _DEV_ENVIRONMENTS


def refuse_mock_backend(setting_name: str, configured: str, real_value: str) -> None:
    """Raise if a mock backend is selected outside development/test."""
    configured_norm = (configured or "").strip().lower()
    if configured_norm == real_value.strip().lower():
        return
    if mock_backends_allowed():
        return
    raise RuntimeError(
        f"{setting_name}={configured!r} is not allowed when "
        f"ENVIRONMENT={settings.environment!r}; set {setting_name}={real_value}"
    )
