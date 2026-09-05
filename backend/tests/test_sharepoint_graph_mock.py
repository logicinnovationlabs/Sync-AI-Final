"""SharePoint Graph mock: pagination, inheritance, groups, links, guests, 429."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.connectors.sharepoint.credentials import DEV_FIXTURE_TOKEN
from app.connectors.sharepoint.graph_client import GraphClient
from app.connectors.sharepoint.oauth import DEFAULT_SCOPES
from app.connectors.sharepoint.graph_mock import (
    ITEM_ANON_LINK,
    ITEM_GROUP,
    ITEM_GUEST,
    ITEM_INHERITED,
    ITEM_ORG_LINK,
    ITEM_UNIQUE,
    MOCK_DELTA_PAGES,
    MOCK_DRIVE_ID,
    MOCK_FILE_COUNT,
    MOCK_GUEST_MAIL,
    MOCK_GUEST_UPN,
    MOCK_GROUP_PAGE2_EMAIL,
    MOCK_MEMBER_EMAIL,
    MOCK_OWNER_EMAIL,
    expected_file_ids,
    mock_session,
    reset_mock_session,
)
from app.connectors.sharepoint.services.sharepoint_service import SharePointConnector
from app.core.models import IdentityHint
from app.identity.resolver import IdentityResolver, _mail_from_guest_upn
from app.normalizer.strategies.sharepoint import SharePointNormalizer
from app.services.registry import DummyTokenStore


def _connector() -> SharePointConnector:
    reset_mock_session()
    return SharePointConnector(
        {
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "connection_scope": "organization",
            "connected_by_email": MOCK_OWNER_EMAIL,
        },
        DummyTokenStore(),
    )


async def _token(*_a, **_k):
    return DEV_FIXTURE_TOKEN, {"dev_fixture": True}


async def _crawl_all(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.sharepoint.services.sharepoint_service.get_sharepoint_access_token",
        _token,
    )
    connector = _connector()
    cursor = None
    docs = []
    pages = 0
    while True:
        result = await connector.fetch_delta(
            since=datetime(1970, 1, 1, tzinfo=timezone.utc), cursor=cursor
        )
        pages += 1
        docs.extend(result.documents)
        if not result.has_more:
            return connector, docs, pages, result
        cursor = result.next_cursor


@pytest.mark.asyncio
async def test_mock_delta_follows_three_pages(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO)
    _connector_obj, docs, pages, last = await _crawl_all(monkeypatch)
    ids = {str(d["id"]).split(":")[-1] for d in docs}
    assert pages == MOCK_DELTA_PAGES
    assert len(docs) == MOCK_FILE_COUNT
    assert ids == set(expected_file_ids())
    assert "Graph retry after 429" in caplog.text or "Graph 429 throttled" in caplog.text
    assert last.has_more is False


@pytest.mark.asyncio
async def test_inherited_walk_uses_parent_library_acl(monkeypatch):
    connector, docs, _pages, _last = await _crawl_all(monkeypatch)
    inherited = next(d for d in docs if str(d["id"]).endswith(ITEM_INHERITED))
    emails = _perm_emails(inherited)
    assert MOCK_MEMBER_EMAIL in emails
    assert MOCK_OWNER_EMAIL in emails
    unified = await connector.transform([inherited])
    assert any(MOCK_MEMBER_EMAIL in p for p in unified[0].permissions)


@pytest.mark.asyncio
async def test_unique_acl_differs_from_parent(monkeypatch):
    connector, docs, _pages, _last = await _crawl_all(monkeypatch)
    unique = next(d for d in docs if str(d["id"]).endswith(ITEM_UNIQUE))
    emails = _perm_emails(unique)
    assert emails == {MOCK_MEMBER_EMAIL}
    unified = await connector.transform([unique])
    assert unified[0].permissions == [f"user:{MOCK_MEMBER_EMAIL}"]


@pytest.mark.asyncio
async def test_group_grant_expands_to_member_email(monkeypatch):
    connector, docs, _pages, _last = await _crawl_all(monkeypatch)
    group_doc = next(d for d in docs if str(d["id"]).endswith(ITEM_GROUP))
    emails = _perm_emails(group_doc)
    assert MOCK_MEMBER_EMAIL in emails
    assert MOCK_GROUP_PAGE2_EMAIL in emails
    unified = await connector.transform([group_doc])
    assert f"user:{MOCK_MEMBER_EMAIL}" in unified[0].permissions
    assert f"user:{MOCK_GROUP_PAGE2_EMAIL}" in unified[0].permissions


@pytest.mark.asyncio
async def test_group_members_follow_two_odata_pages(monkeypatch):
    reset_mock_session()
    from app.connectors.sharepoint.graph_mock import MOCK_GROUP_ID

    client = GraphClient()
    members = await client.list_group_members(DEV_FIXTURE_TOKEN, MOCK_GROUP_ID)
    emails = {
        (m.get("mail") or m.get("userPrincipalName") or "").lower() for m in members
    }
    session = mock_session()
    assert session.group_member_pages_served == [1, 2]
    assert emails == {MOCK_MEMBER_EMAIL, MOCK_GROUP_PAGE2_EMAIL}
    assert len(members) == 2

    _connector, docs, _pages, _last = await _crawl_all(monkeypatch)
    group_doc = next(d for d in docs if str(d["id"]).endswith(ITEM_GROUP))
    unified = await _connector.transform([group_doc])
    assert f"user:{MOCK_MEMBER_EMAIL}" in unified[0].permissions
    assert f"user:{MOCK_GROUP_PAGE2_EMAIL}" in unified[0].permissions
    # Page 2 is not page 1: owner@alpha.test is only on the second members page.
    page1_only = next(d for d in docs if str(d["id"]).endswith(ITEM_UNIQUE))
    unique_unified = await _connector.transform([page1_only])
    assert f"user:{MOCK_GROUP_PAGE2_EMAIL}" not in unique_unified[0].permissions


@pytest.mark.asyncio
async def test_group_members_403_fail_closed_does_not_open_acl():
    """Delegated Graph without GroupMember.Read.All must skip the group, not grant anyone."""
    reset_mock_session()
    client = GraphClient()

    async def _forbidden(_token, url, params=None):
        del _token, params
        raise RuntimeError(f"Graph GET {url} failed: 403 Forbidden")

    client._get = _forbidden  # type: ignore[method-assign]
    from app.connectors.sharepoint.graph_mock import MOCK_GROUP_ID

    members = await client.list_group_members("live-not-fixture-token", MOCK_GROUP_ID)
    assert members == []

    from app.connectors.sharepoint.graph_mock import GROUP_PERMISSIONS
    from app.connectors.sharepoint.services.sharepoint_service import SharePointConnector
    from app.services.registry import DummyTokenStore

    connector = SharePointConnector(
        {"tenant_id": "00000000-0000-0000-0000-000000000001", "connection_scope": "personal"},
        DummyTokenStore(),
    )
    connector.graph_client = client
    expanded = await connector._expand_group_permissions("live-not-fixture-token", GROUP_PERMISSIONS)
    emails = {
        ((p.get("grantedToV2") or {}).get("user") or {}).get("email")
        for p in expanded
        if (p.get("grantedToV2") or {}).get("user")
    }
    emails.discard(None)
    assert emails == set()
    item = {
        "id": "drive:group-file",
        "permissions": expanded,
        "createdBy": {"user": {"email": MOCK_OWNER_EMAIL}},
    }
    resolved = await connector._resolve_permissions(item)
    assert resolved == [f"user:{MOCK_OWNER_EMAIL}"]
    assert not any("*" in p for p in resolved)


def test_delegated_scopes_omit_group_member_read():
    joined = " ".join(DEFAULT_SCOPES)
    assert "GroupMember.Read.All" not in joined
    assert "Sites.Read.All" in joined
    assert "Files.Read.All" in joined
    assert "User.Read" in joined
    assert "offline_access" in joined


def test_delegated_oauth_authority_is_common_not_pinned_tenant(monkeypatch):
    from app.connectors.sharepoint import oauth as sp_oauth

    monkeypatch.setattr(
        sp_oauth.settings, "microsoft_sharepoint_tenant_id", "94f92ea1-e822-43c9-ac1e-6f0110593739"
    )
    assert sp_oauth._sharepoint_authority() == "https://login.microsoftonline.com/common/oauth2/v2.0"
    assert "/common/oauth2/v2.0/authorize" in sp_oauth.sharepoint_authorize_url()
    assert "/common/oauth2/v2.0/token" in sp_oauth.sharepoint_token_url()
    assert "94f92ea1" not in sp_oauth.sharepoint_authorize_url()


@pytest.mark.asyncio
async def test_msa_sites_400_falls_back_to_me_drive():
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
            return {
                "id": "b!msa-onedrive",
                "name": "OneDrive",
                "webUrl": "https://onedrive.live.com/",
                "driveType": "personal",
            }

    connector.graph_client = _Client()
    drives = await connector._enumerate_drives("live-msa-token")
    assert [d["id"] for d in drives] == ["b!msa-onedrive"]
    assert drives[0]["site_name"] == "OneDrive"


@pytest.mark.asyncio
async def test_org_and_anon_links_are_not_anyone(monkeypatch):
    connector, docs, _pages, _last = await _crawl_all(monkeypatch)
    org_link = next(d for d in docs if str(d["id"]).endswith(ITEM_ORG_LINK))
    anon = next(d for d in docs if str(d["id"]).endswith(ITEM_ANON_LINK))
    org_unified = await connector.transform([org_link])
    anon_unified = await connector.transform([anon])
    assert org_unified[0].permissions == [f"user:{MOCK_OWNER_EMAIL}"]
    assert f"user:{MOCK_OWNER_EMAIL}" in anon_unified[0].permissions
    assert not any("*" in p for p in org_unified[0].permissions)
    assert not any("*" in p for p in anon_unified[0].permissions)
    hints = SharePointNormalizer().extract_permission_hints(org_link)
    assert all(h.email != "*" for h, _ in hints)


@pytest.mark.asyncio
async def test_guest_upn_queues_pending_identity_not_minted_user():
    reset_mock_session()
    assert _mail_from_guest_upn(MOCK_GUEST_UPN.lower()) == MOCK_GUEST_MAIL

    class Repo:
        def __init__(self):
            self.pending = []

        async def get_login_user_by_email(self, email, tenant_id):
            del tenant_id
            return None if email == MOCK_GUEST_MAIL else None

        async def upsert_pending_identity(
            self, tenant_id, document_id, email, source_account_id=None
        ):
            self.pending.append({"email": email, "document_id": document_id})

    repo = Repo()
    resolver = IdentityResolver([], repo)
    hint = IdentityHint(
        source_type="sharepoint",
        external_id="aad-guest-1",
        email=MOCK_GUEST_UPN,
        name="External Guest",
    )
    resolved = await resolver.resolve(
        hint, uuid4(), document_id="sharepoint_b!drive:guest"
    )
    assert resolved.is_pending is True
    assert resolved.principal_id is None
    assert repo.pending == [
        {"email": MOCK_GUEST_MAIL, "document_id": "sharepoint_b!drive:guest"}
    ]


def _perm_emails(item: dict) -> set[str]:
    emails = set()
    for perm in item.get("permissions") or []:
        user = ((perm.get("grantedToV2") or {}).get("user") or {})
        email = user.get("email") or user.get("userPrincipalName")
        if email:
            emails.add(str(email).lower())
    return emails
