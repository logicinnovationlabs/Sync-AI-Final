"""P2 ops readiness — startup, health, vault, JWT, routing (no full-app lifespan)."""

import inspect
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.core.exceptions import VaultError
from app.core.health import liveness_payload, readiness_payload
from app.core.startup import StartupConfigurationError, validate_startup_config
from app.services.token_service import TokenService
from app.storage.vault_client import MockVaultClient, get_vault_client


def test_p2_startup_requires_jwt_keys_in_production(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "vault_url", "https://vault.example.com")
    monkeypatch.setattr(settings, "storage_backend", "minio")
    monkeypatch.setattr(settings, "graph_backend", "neo4j")
    monkeypatch.setattr(settings, "signals_backend", "postgres")
    monkeypatch.setattr(settings, "vault_backend", "azure")
    monkeypatch.setattr(settings, "acl_backend", "http")
    missing = tmp_path / "missing.pem"
    monkeypatch.setattr(settings, "jwt_private_key_path", str(missing))
    monkeypatch.setattr(settings, "jwt_public_key_path", str(missing))

    with pytest.raises(StartupConfigurationError, match="JWT private key missing"):
        validate_startup_config()


def test_p2_startup_requires_vault_url_in_production(monkeypatch, tmp_path):
    priv = tmp_path / "private.pem"
    pub = tmp_path / "public.pem"
    priv.write_text("fake-private")
    pub.write_text("fake-public")
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "vault_url", "")
    monkeypatch.setattr(settings, "storage_backend", "minio")
    monkeypatch.setattr(settings, "graph_backend", "neo4j")
    monkeypatch.setattr(settings, "signals_backend", "postgres")
    monkeypatch.setattr(settings, "vault_backend", "azure")
    monkeypatch.setattr(settings, "acl_backend", "http")
    monkeypatch.setattr(settings, "jwt_private_key_path", str(priv))
    monkeypatch.setattr(settings, "jwt_public_key_path", str(pub))

    with pytest.raises(StartupConfigurationError, match="VAULT_URL is required"):
        validate_startup_config()


def test_p2_startup_allows_relaxed_dev(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "storage_backend", "mock")
    monkeypatch.setattr(settings, "graph_backend", "mock")
    monkeypatch.setattr(settings, "signals_backend", "mock")
    monkeypatch.setattr(settings, "vault_backend", "mock")
    monkeypatch.setattr(settings, "acl_backend", "mock")
    validate_startup_config()


def test_p2_token_service_ephemeral_keys_only_in_dev(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "environment", "production")
    missing = tmp_path / "nope.pem"
    monkeypatch.setattr(settings, "jwt_private_key_path", str(missing))
    monkeypatch.setattr(settings, "jwt_public_key_path", str(missing))

    svc = TokenService()
    with pytest.raises(StartupConfigurationError):
        svc._load_keys()


def test_p2_vault_mock_get_raises_on_unknown_secret():
    client = MockVaultClient()
    with pytest.raises(VaultError, match="not found"):
        client.get("kv/tenant/unknown_secret")


def test_p2_vault_mock_refused_outside_dev(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "vault_url", "")
    with pytest.raises(VaultError, match="MockVaultClient is not allowed"):
        get_vault_client()


@pytest.mark.asyncio
async def test_p2_liveness_payload():
    payload = await liveness_payload()
    assert payload["status"] == "alive"
    assert "timestamp" in payload
    assert payload["environment"] == settings.environment


@pytest.mark.asyncio
async def test_p2_readiness_payload_reports_checks():
    with patch("app.core.health._check_postgres", new=AsyncMock(return_value=(True, "ok"))):
        with patch("app.core.health._check_redis", new=AsyncMock(return_value=(True, "ok"))):
            payload = await readiness_payload()
    assert "checks" in payload
    assert payload["checks"]["postgres"]["ok"] is True
    assert payload["checks"]["redis"]["ok"] is True
    assert payload["status"] in ("ready", "not_ready")


def test_p2_main_openapi_disabled_outside_dev():
    import app.main as main_mod

    source = inspect.getsource(main_mod)
    assert "docs_url=\"/docs\" if _is_relaxed_env else None" in source
    assert "openapi_url=\"/openapi.json\" if _is_relaxed_env else None" in source


def test_p2_main_single_router_mount():
    import app.main as main_mod

    source = inspect.getsource(main_mod)
    assert source.count("app.include_router(oauth.router") == 1
    assert source.count("app.include_router(lexical.router") == 1
    assert source.count("app.include_router(identity_routes.router") == 1


def test_p2_rate_limit_middleware_registered():
    import app.main as main_mod

    source = inspect.getsource(main_mod)
    assert "RateLimitMiddleware" in source


def test_p2_celery_beat_schedules_backup():
    from app.workers import celery_app

    import app.workers.beat_schedule  # noqa: F401

    schedule = celery_app.celery_app.conf.beat_schedule
    assert "scheduled-tenant-backups" in schedule
    assert schedule["scheduled-tenant-backups"]["task"] == (
        "app.workers.tasks.run_scheduled_tenant_backups"
    )


def test_p2_backup_checksum_roundtrip(tmp_path, monkeypatch):
    import json
    import hashlib
    from app.scripts import backup as backup_mod

    monkeypatch.setattr(settings, "backup_local_dir", str(tmp_path))
    payload = json.dumps({"schema": "tenant_x", "tables": {"documents": []}}, sort_keys=True)
    checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    backup_mod._persist_artifact("test-backup", payload)
    loaded = backup_mod._load_artifact("test-backup")
    assert hashlib.sha256(loaded.encode("utf-8")).hexdigest() == checksum
