"""SharePoint connector: Graph mock crawl, source tagging, registry discovery."""

from __future__ import annotations

import json

from datetime import datetime, timezone

import pytest

from app.connectors.sharepoint.credentials import (
    DEV_FIXTURE_TOKEN,
    DEV_FIXTURE_VAULT_KEY,
    is_dev_fixture,
    load_app_secret,
    parse_app_secret,
)
from app.connectors.sharepoint.graph_client import (
    FIXTURE_DRIVE_ID,
    GraphClient,
)
from app.connectors.sharepoint.graph_mock import (
    ITEM_INHERITED,
    MOCK_FILE_COUNT,
    reset_mock_session,
)
from app.connectors.sharepoint.services.sharepoint_service import SharePointConnector
from app.core.base_connector import UnifiedDocument
from app.services.registry import ConnectorRegistry, DummyTokenStore


def test_parse_app_secret_requires_keys():
    with pytest.raises(ValueError, match="missing required keys"):
        parse_app_secret({"client_id": "x"})


def test_parse_app_secret_and_fixture_marker():
    info = parse_app_secret(
        json.dumps(
            {
                "azure_tenant_id": "t",
                "client_id": "c",
                "client_secret": "s",
                "dev_fixture": True,
            }
        )
    )
    assert is_dev_fixture(info) is True


def test_registry_discovers_sharepoint():
    registry = ConnectorRegistry()
    registry.discover()
    assert "sharepoint" in registry.list_sources()
    connector = registry.get_connector("sharepoint", {"tenant_id": "t"}, DummyTokenStore())
    assert connector.get_source_type() == "sharepoint"


@pytest.mark.asyncio
async def test_load_app_secret_fixture_key_does_not_need_vault():
    info = await load_app_secret("00000000-0000-0000-0000-000000000001", DEV_FIXTURE_VAULT_KEY)
    assert is_dev_fixture(info) is True
    assert info["client_id"] == "dev-fake-sharepoint-client-id"
    reset_mock_session()
    client = GraphClient()
    delta = await client.list_drive_delta(DEV_FIXTURE_TOKEN, FIXTURE_DRIVE_ID)
    items = delta.get("value") or []
    assert any(i.get("id") == ITEM_INHERITED for i in items)
    assert delta.get("@odata.nextLink")


@pytest.mark.asyncio
async def test_fixture_fetch_delta_normalizes_ids_and_acl(monkeypatch):
    reset_mock_session()

    async def _token(*_a, **_k):
        return DEV_FIXTURE_TOKEN, {"dev_fixture": True}

    monkeypatch.setattr(
        "app.connectors.sharepoint.services.sharepoint_service.get_sharepoint_access_token",
        _token,
    )
    connector = SharePointConnector(
        {
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "connection_scope": "organization",
            "connected_by_email": "admin@synq.dev",
        },
        DummyTokenStore(),
    )
    result = await connector.fetch_delta(
        since=datetime(1970, 1, 1, tzinfo=timezone.utc), cursor=None
    )
    assert result.documents
    assert result.has_more is True
    first = result.documents[0]
    assert first["id"].startswith(f"{FIXTURE_DRIVE_ID}:")
    assert first.get("createdTime")
    assert first.get("modifiedTime")
    assert first.get("source_type") is None
    assert first.get("_extracted_text")

    all_docs = list(result.documents)
    cursor = result.next_cursor
    while result.has_more:
        result = await connector.fetch_delta(
            since=datetime(1970, 1, 1, tzinfo=timezone.utc), cursor=cursor
        )
        all_docs.extend(result.documents)
        cursor = result.next_cursor
    assert len(all_docs) == MOCK_FILE_COUNT

    unified = await connector.transform(all_docs)
    assert unified
    assert all(isinstance(d, UnifiedDocument) for d in unified)
    assert all(d.source_type == "sharepoint" for d in unified)
    assert all(p.startswith("user:") for d in unified for p in d.permissions)
    assert not any("*" in p for d in unified for p in d.permissions)


@pytest.mark.asyncio
async def test_fetch_delta_restarts_when_live_drive_changes(monkeypatch):
    """Completed cursor for account A must not skip account B's OneDrive."""

    async def _token(*_a, **_k):
        return "tok", {}

    monkeypatch.setattr(
        "app.connectors.sharepoint.services.sharepoint_service.get_sharepoint_access_token",
        _token,
    )
    connector = SharePointConnector(
        {"tenant_id": "t", "connection_scope": "personal"},
        DummyTokenStore(),
    )
    live_drive = {
        "id": "newdrive",
        "name": "OneDrive",
        "site_id": "",
        "site_name": "OneDrive",
        "web_url": "https://example",
    }

    async def _enum(_token):
        return [live_drive]

    async def _delta(_token, drive_id, url=None):
        assert drive_id == "newdrive"
        assert url is None
        return {
            "value": [
                {
                    "id": "item1",
                    "name": "a.pdf",
                    "file": {"mimeType": "application/pdf"},
                    "size": 1,
                    "webUrl": "https://example/a.pdf",
                }
            ],
            "@odata.deltaLink": "https://graph/delta-done",
        }

    async def _hydrate(_token, files):
        return files

    monkeypatch.setattr(connector, "_enumerate_drives", _enum)
    monkeypatch.setattr(connector.graph_client, "list_drive_delta", _delta)
    monkeypatch.setattr(connector, "_hydrate_files", _hydrate)

    stale = json.dumps(
        {
            "drives": [
                {
                    "id": "olddrive",
                    "name": "OneDrive",
                    "site_id": "",
                    "site_name": "OneDrive",
                    "web_url": "",
                }
            ],
            "drive_idx": 1,
            "next_link": None,
            "delta_links": {"olddrive": "https://graph/old"},
        }
    )
    result = await connector.fetch_delta(
        since=datetime(1970, 1, 1, tzinfo=timezone.utc), cursor=stale
    )
    assert result.documents
    assert result.documents[0]["id"].startswith("newdrive:")


def _personal_connector(monkeypatch):
    async def _token(*_a, **_k):
        return "tok", {}

    monkeypatch.setattr(
        "app.connectors.sharepoint.services.sharepoint_service.get_sharepoint_access_token",
        _token,
    )
    return SharePointConnector(
        {"tenant_id": "t", "connection_scope": "personal"},
        DummyTokenStore(),
    )


@pytest.mark.asyncio
async def test_fetch_delta_picks_up_new_file_after_first_crawl(monkeypatch):
    connector = _personal_connector(monkeypatch)
    live_drive = {
        "id": "livedrive",
        "name": "OneDrive",
        "site_id": "",
        "site_name": "OneDrive",
        "web_url": "https://example",
    }
    seen_urls = []

    async def _enum(_token):
        return [live_drive]

    async def _delta(_token, drive_id, url=None):
        seen_urls.append(url)
        assert drive_id == "livedrive"
        return {
            "value": [
                {
                    "id": "new-upload",
                    "name": "fresh.pdf",
                    "file": {"mimeType": "application/pdf"},
                    "size": 12,
                    "webUrl": "https://example/fresh.pdf",
                }
            ],
            "@odata.deltaLink": "https://graph/delta-next",
        }

    async def _hydrate(_token, files):
        return files

    monkeypatch.setattr(connector, "_enumerate_drives", _enum)
    monkeypatch.setattr(connector.graph_client, "list_drive_delta", _delta)
    monkeypatch.setattr(connector, "_hydrate_files", _hydrate)

    completed = json.dumps(
        {
            "drives": [live_drive],
            "drive_idx": 1,
            "next_link": None,
            "delta_links": {"livedrive": "https://graph/delta-prev"},
        }
    )
    result = await connector.fetch_delta(
        since=datetime(1970, 1, 1, tzinfo=timezone.utc), cursor=completed
    )
    assert seen_urls == ["https://graph/delta-prev"]
    assert result.documents[0]["name"] == "fresh.pdf"
    assert result.documents[0]["id"].startswith("livedrive:")
    assert result.has_more is False
    state = json.loads(result.next_cursor)
    assert state["delta_links"]["livedrive"] == "https://graph/delta-next"


@pytest.mark.asyncio
async def test_fetch_delta_reports_removed_ids_on_incremental(monkeypatch):
    connector = _personal_connector(monkeypatch)
    live_drive = {
        "id": "livedrive",
        "name": "OneDrive",
        "site_id": "",
        "site_name": "OneDrive",
        "web_url": "",
    }

    async def _enum(_token):
        return [live_drive]

    async def _delta(_token, drive_id, url=None):
        del drive_id, url
        return {
            "value": [{"id": "gone", "@removed": {"reason": "deleted"}}],
            "@odata.deltaLink": "https://graph/delta-next",
        }

    monkeypatch.setattr(connector, "_enumerate_drives", _enum)
    monkeypatch.setattr(connector.graph_client, "list_drive_delta", _delta)

    completed = json.dumps(
        {
            "drives": [live_drive],
            "drive_idx": 1,
            "delta_links": {"livedrive": "https://graph/delta-prev"},
        }
    )
    result = await connector.fetch_delta(
        since=datetime(1970, 1, 1, tzinfo=timezone.utc), cursor=completed
    )
    assert result.documents == []
    assert result.deleted_ids == ["livedrive:gone"]


def test_enqueue_sharepoint_poll_skips_in_flight_sync():
    from app.workers.sharepoint_poll import (
        enqueue_sharepoint_delta_poll,
        split_cursor_scope,
    )

    delayed = []
    result = enqueue_sharepoint_delta_poll(
        ["tid:uid", "tid:organization"],
        is_syncing=lambda _t, user_id: user_id == "uid",
        delay=lambda **kwargs: delayed.append(kwargs),
        acquire_lock=lambda _t, _u: True,
    )
    assert split_cursor_scope("tid:uid") == ("tid", "uid")
    assert result["enqueued"] == 1
    assert result["skipped"] == 1
    assert delayed[0]["source_type"] == "sharepoint"
    assert delayed[0]["user_id"] == "organization"


def test_graph_resync_required_detects_410():
    from app.connectors.sharepoint.graph_client import graph_error_is_resync_required

    assert graph_error_is_resync_required(
        "Graph GET https://graph.microsoft.com/v1.0/drives/x/root/delta failed: 410 gone resyncRequired"
    )
    assert graph_error_is_resync_required("resyncRequired")
    assert not graph_error_is_resync_required("Graph GET /me/drive failed: 403")
