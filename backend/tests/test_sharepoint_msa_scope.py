"""MSA vs work/school Sites.Read.All carve-out, and durable token persist."""

from __future__ import annotations

import base64
import json

import pytest

from app.connectors.sharepoint.oauth import (
    MSA_CONSUMER_TENANT_ID,
    is_personal_microsoft_account,
    missing_scopes_block_connect,
)
from app.connectors.sharepoint.services.sharepoint_service import SharePointConnector
from app.connectors.sharepoint.token_store import PersistentSharePointTokenStore
from app.services.registry import DummyTokenStore


def _unsigned_jwt(**claims) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


def _msa_token(**extra):
    data = {
        "access_token": _unsigned_jwt(tid=MSA_CONSUMER_TENANT_ID, idp="live.com"),
        "_missing_scopes": ["Sites.Read.All"],
    }
    data.update(extra)
    return data


def _work_token(**extra):
    data = {
        "access_token": _unsigned_jwt(
            tid="94f92ea1-e822-43c9-ac1e-6f0110593739",
            idp="https://sts.windows.net/94f92ea1-e822-43c9-ac1e-6f0110593739/",
        ),
        "_missing_scopes": ["Sites.Read.All"],
    }
    data.update(extra)
    return data


def test_personal_account_missing_sites_read_all_connects():
    token = _msa_token()
    assert is_personal_microsoft_account(token) is True
    assert missing_scopes_block_connect(token) is False


def test_work_school_account_missing_sites_read_all_still_errors():
    token = _work_token()
    assert is_personal_microsoft_account(token) is False
    assert missing_scopes_block_connect(token) is True


def test_personal_account_missing_files_read_all_still_errors():
    token = _msa_token(_missing_scopes=["Files.Read.All"])
    assert missing_scopes_block_connect(token) is True


def test_opaque_token_missing_sites_fails_closed():
    token = {"access_token": "not-a-jwt", "_missing_scopes": ["Sites.Read.All"]}
    assert is_personal_microsoft_account(token) is False
    assert missing_scopes_block_connect(token) is True


def test_live_msa_opaque_token_uses_nonguid_me_id():
    """Live Graph MSA access tokens are opaque; /me.id is 16-char, not an Entra UUID."""
    token = {"access_token": "EwB" + "x" * 80, "_missing_scopes": ["Sites.Read.All"]}
    profile = {"id": "0123456789abcdef", "userPrincipalName": "user@example.com"}
    assert is_personal_microsoft_account(token, me_profile=profile) is True
    assert missing_scopes_block_connect(token, me_profile=profile) is False


def test_work_school_guid_me_id_missing_sites_still_errors():
    token = {"access_token": "EwB" + "x" * 80, "_missing_scopes": ["Sites.Read.All"]}
    profile = {"id": "94f92ea1-e822-43c9-ac1e-6f0110593739"}
    assert is_personal_microsoft_account(token, me_profile=profile) is False
    assert missing_scopes_block_connect(token, me_profile=profile) is True


def test_work_jwt_tid_wins_over_nonguid_me_id():
    token = _work_token()
    profile = {"id": "0123456789abcdef"}
    assert is_personal_microsoft_account(token, me_profile=profile) is False
    assert missing_scopes_block_connect(token, me_profile=profile) is True


def test_live_com_idp_without_tid_is_personal():
    token = {
        "access_token": _unsigned_jwt(idp="live.com"),
        "_missing_scopes": ["Sites.Read.All"],
    }
    assert is_personal_microsoft_account(token) is True
    assert missing_scopes_block_connect(token) is False


def test_me_identities_live_issuer_is_personal():
    token = {"access_token": "opaque", "_missing_scopes": ["Sites.Read.All"]}
    profile = {"identities": [{"issuer": "https://login.live.com", "issuerAssignedId": "x"}]}
    assert is_personal_microsoft_account(token, me_profile=profile) is True
    assert missing_scopes_block_connect(token, me_profile=profile) is False


@pytest.mark.asyncio
async def test_set_token_writes_vault_before_return_when_loop_running(monkeypatch):
    calls = []

    class _Vault:
        def set(self, key, value):
            calls.append((key, value))

        def get(self, key):
            for stored_key, stored_value in reversed(calls):
                if stored_key == key:
                    return stored_value
            raise KeyError(key)

    monkeypatch.setattr("app.connectors.sharepoint.token_store.vault_client", _Vault())
    monkeypatch.setattr("app.connectors.sharepoint.token_store._sync_redis", lambda: None)
    store = PersistentSharePointTokenStore("tenant-a")
    payload = {"access_token": "live-token", "refresh_token": "r"}
    store.set_token("sharepoint_oauth:tenant-a:user-1:personal", payload)
    assert calls, "Vault write must complete before set_token returns"
    assert json.loads(calls[0][1])["access_token"] == "live-token"
    got = store.get_token("sharepoint_oauth:tenant-a:user-1:personal")
    assert got["access_token"] == "live-token"


@pytest.mark.asyncio
async def test_get_token_reads_vault_when_event_loop_is_running(monkeypatch):
    blob = json.dumps({"access_token": "from-vault"})

    class _Vault:
        def get(self, key):
            del key
            return blob

        def set(self, key, value):
            del key, value

    monkeypatch.setattr("app.connectors.sharepoint.token_store.vault_client", _Vault())
    monkeypatch.setattr("app.connectors.sharepoint.token_store._sync_redis", lambda: None)
    store = PersistentSharePointTokenStore("tenant-a")
    got = store.get_token("sharepoint_oauth:tenant-a:user-1:personal")
    assert got["access_token"] == "from-vault"


@pytest.mark.asyncio
async def test_me_drive_403_is_not_swallowed():
    connector = SharePointConnector(
        {"tenant_id": "t", "connection_scope": "personal"}, DummyTokenStore()
    )

    class _Client:
        async def list_sites(self, *args, **kwargs):
            del args, kwargs
            raise RuntimeError(
                "Graph GET https://graph.microsoft.com/v1.0/sites failed: 400 "
                '{"error":{"code":"BadRequest","message":"This API is not supported for MSA accounts"}}'
            )

        async def get_my_drive(self, access_token):
            del access_token
            raise RuntimeError(
                "Graph GET https://graph.microsoft.com/v1.0/me/drive failed: 403 "
                '{"error":{"code":"accessDenied","message":"Access denied"}}'
            )

    connector.graph_client = _Client()
    with pytest.raises(RuntimeError, match="me/drive failed: 403"):
        await connector._enumerate_drives("live-msa-token")


@pytest.mark.asyncio
async def test_graph_list_sites_msa_400_returns_empty_not_error():
    from app.connectors.sharepoint.graph_client import GraphClient

    client = GraphClient()

    async def boom(_token, url, params=None):
        del params
        raise RuntimeError(
            f"Graph GET {url} failed: 400 "
            '{"error":{"code":"BadRequest","message":"This API is not supported for MSA accounts"}}'
        )

    client._get = boom  # type: ignore[method-assign]
    data = await client.list_sites("live-msa-token")
    assert data == {"value": []}


@pytest.mark.asyncio
async def test_graph_list_sites_other_400_still_raises():
    from app.connectors.sharepoint.graph_client import GraphClient

    client = GraphClient()

    async def boom(_token, url, params=None):
        del params
        raise RuntimeError(
            f"Graph GET {url} failed: 400 "
            '{"error":{"code":"BadRequest","message":"Invalid request"}}'
        )

    client._get = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="Invalid request"):
        await client.list_sites("work-token")
