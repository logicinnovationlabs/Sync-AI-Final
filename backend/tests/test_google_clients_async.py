"""
Unit tests for async Google clients (GmailClient, DriveClient),
watch expiration handling, and Principal UUIDv5 support.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
import pytest
import respx
import httpx

from app.connectors.google.clients.gmail_client import GmailClient, GMAIL_ROOT
from app.connectors.google.clients.drive_client import DriveClient, DRIVE_ROOT
from app.core.models import Principal, ACLEntry, PermissionLevel


@respx.mock
@pytest.mark.asyncio
async def test_gmail_client_list_messages(respx_mock):
    client = GmailClient()
    respx_mock.route(url__startswith=f"{GMAIL_ROOT}/messages").respond(
        200,
        json={
            "messages": [{"id": "msg1"}, {"id": "msg2"}],
            "nextPageToken": "tok123",
        },
    )
    res = await client.list_messages("test-token", page_size=50, query="is:unread")
    assert len(res["messages"]) == 2
    assert res["nextPageToken"] == "tok123"


@respx.mock
@pytest.mark.asyncio
async def test_gmail_client_get_message(respx_mock):
    client = GmailClient()
    respx_mock.route(url__startswith=f"{GMAIL_ROOT}/messages/msg123").respond(
        200,
        json={
            "id": "msg123",
            "threadId": "th123",
            "snippet": "Hello world",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                ],
                "body": {"data": "SGVsbG8gV29ybGQ="},
            },
        },
    )
    res = await client.get_message("test-token", "msg123")
    assert res["id"] == "msg123"
    assert client.extract_header(res, "Subject") == "Test Subject"
    assert client.extract_header(res, "From") == "sender@example.com"
    assert client.decode_message_body(res["payload"]) == "Hello World"


@respx.mock
@pytest.mark.asyncio
async def test_gmail_client_list_history_404_fallback(respx_mock):
    client = GmailClient()
    respx_mock.route(url__startswith=f"{GMAIL_ROOT}/history").respond(404)
    res = await client.list_history("test-token", start_history_id="100")
    assert res == {"history": [], "historyId": "100"}


@respx.mock
@pytest.mark.asyncio
async def test_gmail_client_watch(respx_mock):
    client = GmailClient()
    respx_mock.route(url__startswith=f"{GMAIL_ROOT}/watch").respond(
        200,
        json={"historyId": "12345", "expiration": "1788773910000"},
    )
    res = await client.watch("test-token", topic_name="projects/p/topics/t")
    assert res["historyId"] == "12345"
    assert res["expiration"] == "1788773910000"


@respx.mock
@pytest.mark.asyncio
async def test_drive_client_list_files(respx_mock):
    client = DriveClient()
    respx_mock.route(url__startswith=f"{DRIVE_ROOT}/files").respond(
        200,
        json={
            "files": [
                {"id": "f1", "name": "Doc1.pdf", "mimeType": "application/pdf"},
                {"id": "f2", "name": "Sheet1", "mimeType": "application/vnd.google-apps.spreadsheet"},
            ],
            "nextPageToken": "p2",
        },
    )
    res = await client.list_files("test-token", page_size=10)
    assert len(res["files"]) == 2
    assert res["nextPageToken"] == "p2"


@respx.mock
@pytest.mark.asyncio
async def test_drive_client_list_permissions(respx_mock):
    client = DriveClient()
    respx_mock.route(url__startswith=f"{DRIVE_ROOT}/files/f1/permissions").respond(
        200,
        json={
            "permissions": [
                {"id": "p1", "type": "user", "role": "owner", "emailAddress": "user@example.com"},
            ]
        },
    )
    perms = await client.list_permissions("test-token", "f1")
    assert len(perms) == 1
    assert perms[0]["emailAddress"] == "user@example.com"


@respx.mock
@pytest.mark.asyncio
async def test_drive_client_export_and_download(respx_mock):
    client = DriveClient()
    respx_mock.route(url__startswith=f"{DRIVE_ROOT}/files/f1/export").respond(
        200, content=b"exported plain text"
    )
    respx_mock.route(url__startswith=f"{DRIVE_ROOT}/files/f2").respond(
        200, content=b"binary pdf bytes"
    )

    exp = await client.export_file("test-token", "f1", "text/plain")
    assert exp == b"exported plain text"

    dl = await client.download_file("test-token", "f2")
    assert dl == b"binary pdf bytes"


def test_principal_supports_uuidv5():
    tenant_id_v5 = uuid.uuid5(uuid.NAMESPACE_DNS, "syncai.test")
    principal_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    principal = Principal(
        id=principal_id,
        tenant_id=tenant_id_v5,
        email="syncai740@gmail.com",
        name="Sync AI",
        source_identities={"google_gmail": "syncai740@gmail.com"},
        created_at=now,
        updated_at=now,
    )
    assert principal.tenant_id == tenant_id_v5
    assert principal.email == "syncai740@gmail.com"


def test_acl_entry_supports_uuidv5_and_group():
    tenant_id_v5 = uuid.uuid5(uuid.NAMESPACE_DNS, "syncai.test")
    now = datetime.now(timezone.utc)
    entry = ACLEntry(
        document_id="google_drive_f1",
        principal_id=uuid.uuid4(),
        permission=PermissionLevel.OWNER,
        granted_via="direct",
        source_type="google_drive",
        tenant_id=tenant_id_v5,
        created_at=now,
        updated_at=now,
    )
    assert entry.tenant_id == tenant_id_v5
