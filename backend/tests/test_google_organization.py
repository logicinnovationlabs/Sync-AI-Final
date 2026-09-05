"""Google Workspace (Organization) connector wiring — no ACL changes."""

from types import SimpleNamespace
from uuid import uuid4

from app.connectors.google.keys import cursor_scope_id
from app.connectors.google.services.drive_service import DriveConnector
from app.connectors.router import (
    is_organization_google_connected,
    organization_cursor_scope_id,
)
from app.services.registry import DummyTokenStore


def test_org_status_treats_oauth_admin_as_connected():
    row = SimpleNamespace(
        enabled=True,
        config={"credential_mode": "oauth_admin", "connected_by": str(uuid4())},
    )
    assert is_organization_google_connected(row) is True


def test_org_status_treats_dwd_as_connected():
    row = SimpleNamespace(
        enabled=True,
        config={"credential_mode": "service_account_dwd"},
    )
    assert is_organization_google_connected(row) is True


def test_org_status_rejects_disabled_or_missing_row():
    assert is_organization_google_connected(None) is False
    assert (
        is_organization_google_connected(
            SimpleNamespace(enabled=False, config={"credential_mode": "oauth_admin"})
        )
        is False
    )


def test_organization_cursor_matches_worker_key():
    tenant_id = str(uuid4())
    assert organization_cursor_scope_id(tenant_id) == cursor_scope_id(
        tenant_id, "organization"
    )
    assert organization_cursor_scope_id(tenant_id) != f"{tenant_id}_organization"


def test_drive_connector_reads_org_scope_from_config():
    connector = DriveConnector(
        {"tenant_id": str(uuid4()), "connection_scope": "organization"},
        DummyTokenStore(),
    )
    assert connector.connection_scope == "organization"
