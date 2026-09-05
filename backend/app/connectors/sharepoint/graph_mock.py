"""Realistic Microsoft Graph response shapes for SharePoint (no live Azure).

This module replaces the 2-file uniform-ACL fixture. It never calls Microsoft
and never needs a client ID or secret. Token ``dev-fixture-token`` selects it.

Link-share decision (fail closed):
    Graph ``permission.link.scope`` of ``anonymous``, ``organization``, or
    ``users`` has no user/group identity. Those entries are **not** mapped into
    ``acl_filter_terms``. They are skipped. A file whose only extra grant is a
    link is indexed with owner (createdBy) only — never ``user:*`` / tenant-wide
    default. That default was previously eliminated elsewhere in this project.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

logger_name = "app.connectors.sharepoint.graph_mock"

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

MOCK_SITE_ID = (
    "contoso.sharepoint.com,00000000-0000-0000-0000-000000000001,"
    "00000000-0000-0000-0000-000000000002"
)
MOCK_DRIVE_ID = "b!dev-fake-sharepoint-drive"
MOCK_LIBRARY_ROOT_ID = "01DEVFAKELIBRARYROOT"
MOCK_GROUP_ID = "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"

# Seeded alpha tenant emails (lookups only — never inserted by this mock).
MOCK_OWNER_EMAIL = "admin@synq.dev"
MOCK_MEMBER_EMAIL = "member@alpha.test"
# Seeded owner@alpha.test — page-2 Finance group member (not on page 1).
MOCK_GROUP_PAGE2_EMAIL = "owner@alpha.test"
MOCK_GUEST_UPN = "guest.user@external.com#EXT#@contoso.onmicrosoft.com"
MOCK_GUEST_MAIL = "guest.user@external.com"

ITEM_INHERITED = "01ITEMINHERITED0001"
ITEM_UNIQUE = "01ITEMUNIQUEACL0002"
ITEM_GROUP = "01ITEMGROUPGRANT0003"
ITEM_ORG_LINK = "01ITEMORGLINK0004"
ITEM_GUEST = "01ITEMGUESTSHARE0005"
ITEM_ANON_LINK = "01ITEMANYONELINK0006"
ITEM_FOLDER = "01ITEMFOLDERIGNORED"

MOCK_FILE_COUNT = 6
MOCK_DELTA_PAGES = 3

# Compat aliases used by older tests / reports.
FIXTURE_SITE_ID = MOCK_SITE_ID
FIXTURE_DRIVE_ID = MOCK_DRIVE_ID
FIXTURE_ITEM_ID = ITEM_INHERITED
FIXTURE_ITEM_ID_DENIED = ITEM_UNIQUE


class GraphThrottled(Exception):
    """HTTP 429 from Graph. ``retry_after`` is seconds from Retry-After."""

    def __init__(self, retry_after: float, url: str):
        self.retry_after = retry_after
        self.url = url
        super().__init__(f"Graph 429 Retry-After={retry_after} url={url}")


def _user(email: str, user_id: str, name: str) -> Dict[str, Any]:
    return {"user": {"id": user_id, "email": email, "displayName": name, "userPrincipalName": email}}


def _owner_created_by() -> Dict[str, Any]:
    return {
        "user": {
            "id": "aad-admin-1",
            "email": MOCK_OWNER_EMAIL,
            "displayName": "Alpha Admin",
            "userPrincipalName": MOCK_OWNER_EMAIL,
        }
    }


def _file(
    item_id: str,
    name: str,
    text: str,
    *,
    folder: bool = False,
    inherited_from: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "id": item_id,
        "name": name,
        "webUrl": f"https://contoso.sharepoint.com/sites/Team/Shared%20Documents/{name.replace(' ', '%20')}",
        "createdDateTime": "2026-09-01T10:00:00Z",
        "lastModifiedDateTime": "2026-09-03T08:00:00Z",
        "size": max(len(text), 64),
        "createdBy": _owner_created_by(),
        "lastModifiedBy": _owner_created_by(),
        "parentReference": {"driveId": MOCK_DRIVE_ID, "id": MOCK_LIBRARY_ROOT_ID},
        "_extracted_text": text,
    }
    if folder:
        item["folder"] = {"childCount": 0}
    else:
        item["file"] = {"mimeType": "text/plain" if name.endswith(".txt") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if inherited_from:
        item["inheritedFrom"] = inherited_from
    return item


LIBRARY_PERMISSIONS: List[Dict[str, Any]] = [
    {
        "id": "perm-library-owner",
        "roles": ["owner"],
        "grantedToV2": _user(MOCK_OWNER_EMAIL, "aad-admin-1", "Alpha Admin"),
    },
    {
        "id": "perm-library-member",
        "roles": ["read"],
        "grantedToV2": _user(MOCK_MEMBER_EMAIL, "aad-member-1", "Alpha Member"),
    },
]

INHERITED_FROM_LIBRARY = {"driveId": MOCK_DRIVE_ID, "id": MOCK_LIBRARY_ROOT_ID}

# Unique / broken inheritance — only member, not the library owner grant.
UNIQUE_PERMISSIONS: List[Dict[str, Any]] = [
    {
        "id": "perm-unique-member",
        "roles": ["read"],
        "grantedToV2": _user(MOCK_MEMBER_EMAIL, "aad-member-1", "Alpha Member"),
    }
]

GROUP_PERMISSIONS: List[Dict[str, Any]] = [
    {
        "id": "perm-aad-group-finance",
        "roles": ["read"],
        "grantedToV2": {
            "group": {
                "id": MOCK_GROUP_ID,
                "displayName": "Finance",
            }
        },
    }
]

ORG_LINK_PERMISSIONS: List[Dict[str, Any]] = [
    {
        "id": "perm-org-view-link",
        "roles": ["read"],
        "link": {
            "scope": "organization",
            "type": "view",
            "preventsDownload": False,
        },
    }
]

GUEST_PERMISSIONS: List[Dict[str, Any]] = [
    {
        "id": "perm-guest-ext",
        "roles": ["read"],
        "grantedToV2": {
            "user": {
                "id": "aad-guest-1",
                "email": MOCK_GUEST_UPN,
                "userPrincipalName": MOCK_GUEST_UPN,
                "displayName": "External Guest",
            }
        },
    }
]

ANON_LINK_PERMISSIONS: List[Dict[str, Any]] = [
    {
        "id": "perm-anyone-link",
        "roles": ["read"],
        "link": {
            "scope": "anonymous",
            "type": "view",
        },
    },
    {
        "id": "perm-anyone-owner",
        "roles": ["owner"],
        "grantedToV2": _user(MOCK_OWNER_EMAIL, "aad-admin-1", "Alpha Admin"),
    },
]

def _group_member(user_id: str, email: str, name: str) -> Dict[str, Any]:
    return {
        "id": user_id,
        "@odata.type": "#microsoft.graph.user",
        "displayName": name,
        "mail": email,
        "userPrincipalName": email,
    }


GROUP_MEMBERS_PAGE_1: List[Dict[str, Any]] = [
    _group_member("aad-member-1", MOCK_MEMBER_EMAIL, "Alpha Member"),
]
GROUP_MEMBERS_PAGE_2: List[Dict[str, Any]] = [
    _group_member("aad-owner-1", MOCK_GROUP_PAGE2_EMAIL, "Alpha Owner"),
]
GROUP_MEMBERS: List[Dict[str, Any]] = GROUP_MEMBERS_PAGE_1 + GROUP_MEMBERS_PAGE_2
GROUP_MEMBERS_NEXT = (
    f"{GRAPH_BASE}/groups/{MOCK_GROUP_ID}/members?$skiptoken=mock-members-page-2"
)

FILES: Dict[str, Dict[str, Any]] = {
    ITEM_INHERITED: _file(
        ITEM_INHERITED,
        "Inherited From Library.docx",
        "Inherited ACL file. Effective grants come from the parent library, not unique ACLs.",
        inherited_from=INHERITED_FROM_LIBRARY,
    ),
    ITEM_UNIQUE: _file(
        ITEM_UNIQUE,
        "Broken Inheritance Unique.txt",
        "Unique permissions. Only member@alpha.test is granted; library owner is not on this ACL.",
    ),
    ITEM_GROUP: _file(
        ITEM_GROUP,
        "Finance Group Grant.docx",
        "Granted to Azure AD security group Finance, not a direct user ACE.",
    ),
    ITEM_ORG_LINK: _file(
        ITEM_ORG_LINK,
        "Organization Link Only.txt",
        "Shared via organization-wide link. Must not become tenant-wide acl_filter_terms.",
    ),
    ITEM_GUEST: _file(
        ITEM_GUEST,
        "Guest External Share.docx",
        "Shared with a guest UPN that is not a platform user.",
    ),
    ITEM_ANON_LINK: _file(
        ITEM_ANON_LINK,
        "Anyone With The Link.pdf",
        "Anonymous view link plus owner. Anonymous link must not map to user:*.",
    ),
}

FOLDER = _file(ITEM_FOLDER, "Archive Folder", "", folder=True)

PERMISSIONS_BY_ITEM: Dict[str, List[Dict[str, Any]]] = {
    MOCK_LIBRARY_ROOT_ID: LIBRARY_PERMISSIONS,
    # Empty unique list + inheritedFrom on the item → client must walk parent.
    ITEM_INHERITED: [],
    ITEM_UNIQUE: UNIQUE_PERMISSIONS,
    ITEM_GROUP: GROUP_PERMISSIONS,
    ITEM_ORG_LINK: ORG_LINK_PERMISSIONS,
    ITEM_GUEST: GUEST_PERMISSIONS,
    ITEM_ANON_LINK: ANON_LINK_PERMISSIONS,
}

DELTA_PAGE_1 = [FOLDER, FILES[ITEM_INHERITED], FILES[ITEM_UNIQUE]]
DELTA_PAGE_2 = [FILES[ITEM_GROUP], FILES[ITEM_ORG_LINK]]
DELTA_PAGE_3 = [FILES[ITEM_GUEST], FILES[ITEM_ANON_LINK]]

PAGE2_NEXT = f"{GRAPH_BASE}/drives/{MOCK_DRIVE_ID}/root/delta?$skiptoken=mock-page-2"
PAGE3_NEXT = f"{GRAPH_BASE}/drives/{MOCK_DRIVE_ID}/root/delta?$skiptoken=mock-page-3"
DELTA_LINK = f"{GRAPH_BASE}/drives/{MOCK_DRIVE_ID}/root/delta?token=mock-delta-complete"


def expected_file_ids() -> List[str]:
    return [
        ITEM_INHERITED,
        ITEM_UNIQUE,
        ITEM_GROUP,
        ITEM_ORG_LINK,
        ITEM_GUEST,
        ITEM_ANON_LINK,
    ]


class MockGraphSession:
    """In-process Graph. One 429 on the first page-2 delta request."""

    def __init__(self) -> None:
        self.page2_attempts = 0
        self.delta_pages_served: List[int] = []
        self.group_member_pages_served: List[int] = []

    def reset(self) -> None:
        self.page2_attempts = 0
        self.delta_pages_served = []
        self.group_member_pages_served = []

    def list_sites(self, site_url: Optional[str] = None) -> Dict[str, Any]:
        return {
            "value": [
                {
                    "id": MOCK_SITE_ID,
                    "displayName": "Team Site",
                    "name": "Team",
                    "webUrl": site_url or "https://contoso.sharepoint.com/sites/Team",
                }
            ]
        }

    def list_drives(self, site_id: str) -> Dict[str, Any]:
        del site_id
        return {
            "value": [
                {
                    "id": MOCK_DRIVE_ID,
                    "name": "Documents",
                    "webUrl": "https://contoso.sharepoint.com/sites/Team/Shared Documents",
                    "driveType": "documentLibrary",
                }
            ]
        }

    def list_drive_delta(self, drive_id: str, url: Optional[str] = None) -> Dict[str, Any]:
        del drive_id
        page = _delta_page_from_url(url)
        if page == 2:
            self.page2_attempts += 1
            if self.page2_attempts == 1:
                raise GraphThrottled(retry_after=0, url=url or PAGE2_NEXT)
        self.delta_pages_served.append(page)
        if page == 1:
            return {"value": [dict(x) for x in DELTA_PAGE_1], "@odata.nextLink": PAGE2_NEXT}
        if page == 2:
            return {"value": [dict(x) for x in DELTA_PAGE_2], "@odata.nextLink": PAGE3_NEXT}
        if page == 0:
            return {"value": [], "@odata.deltaLink": DELTA_LINK}
        return {"value": [dict(x) for x in DELTA_PAGE_3], "@odata.deltaLink": DELTA_LINK}

    def list_permissions(self, drive_id: str, item_id: str) -> List[Dict[str, Any]]:
        del drive_id
        raw = PERMISSIONS_BY_ITEM.get(item_id)
        if raw is None:
            return []
        return [dict(p) for p in raw]

    def list_group_members(
        self, group_id: str, url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Graph page shape. Page 1 sets ``@odata.nextLink``; page 2 does not."""
        wanted = group_id == MOCK_GROUP_ID or (url or "").find(MOCK_GROUP_ID) >= 0
        if not wanted:
            return {"value": []}
        page = 2 if url and "mock-members-page-2" in url else 1
        self.group_member_pages_served.append(page)
        if page == 1:
            return {
                "value": [dict(m) for m in GROUP_MEMBERS_PAGE_1],
                "@odata.nextLink": GROUP_MEMBERS_NEXT,
            }
        return {"value": [dict(m) for m in GROUP_MEMBERS_PAGE_2]}

    def download_content(self, drive_id: str, item_id: str) -> bytes:
        del drive_id
        item = FILES.get(item_id)
        if not item:
            return b""
        return str(item.get("_extracted_text") or item.get("name") or "").encode("utf-8")


def _delta_page_from_url(url: Optional[str]) -> int:
    if not url:
        return 1
    parsed = urlparse(url)
    token = (parse_qs(parsed.query).get("$skiptoken") or parse_qs(parsed.query).get("skiptoken") or [""])[0]
    if "page-2" in token or "page-2" in url:
        return 2
    if "page-3" in token or "page-3" in url:
        return 3
    if "mock-delta-complete" in url:
        return 0
    return 1


_SESSION = MockGraphSession()


def mock_session() -> MockGraphSession:
    return _SESSION


def reset_mock_session() -> MockGraphSession:
    _SESSION.reset()
    return _SESSION
