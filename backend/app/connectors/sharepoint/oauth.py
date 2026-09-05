"""Delegated Microsoft Graph OAuth for member-level SharePoint connections."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Microsoft's well-known consumer (MSA) tenant. Personal accounts always
# carry this `tid` in Graph v2 JWTs. Work/school tenants use a different GUID.
MSA_CONSUMER_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"


def decode_unverified_jwt_claims(token: str) -> Dict[str, Any]:
    """Decode a JWT payload without verifying the signature.

    Used only to read `tid` / `idp` from a Graph token we already received
    over TLS from login.microsoftonline.com. Opaque (non-JWT) tokens return {}.
    """
    parts = (token or "").split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    pad = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload + pad)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _is_aad_object_guid(value: str) -> bool:
    """Entra work/school Graph user ids are UUIDs. MSA /me.id is not."""
    raw = (value or "").strip()
    if len(raw) != 36:
        return False
    parts = raw.split("-")
    if [len(p) for p in parts] != [8, 4, 4, 4, 12]:
        return False
    return all(c in "0123456789abcdefABCDEF" for c in raw if c != "-")


def microsoft_account_signals(
    token_data: Optional[Dict[str, Any]] = None,
    me_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the account-type signals actually present on the token/profile."""
    blob = token_data or {}
    tid = ""
    idp = ""
    source = ""
    for field in ("id_token", "access_token"):
        claims = decode_unverified_jwt_claims(str(blob.get(field) or ""))
        if not claims:
            continue
        tid = str(claims.get("tid") or "")
        idp = str(claims.get("idp") or "")
        if tid or idp:
            source = field
            break
    profile = me_profile or {}
    issuers = []
    for identity in profile.get("identities") or []:
        if isinstance(identity, dict) and identity.get("issuer"):
            issuers.append(str(identity.get("issuer")))
    me_id = str(profile.get("id") or "")
    return {
        "tid": tid,
        "idp": idp,
        "jwt_source": source,
        "me_id": me_id,
        "me_id_is_guid": _is_aad_object_guid(me_id),
        "me_user_type": str(profile.get("userType") or ""),
        "identity_issuers": issuers,
    }


def is_personal_microsoft_account(
    token_data: Optional[Dict[str, Any]] = None,
    me_profile: Optional[Dict[str, Any]] = None,
) -> bool:
    """True only when Graph/token evidence says this is an MSA, not work/school.

    Live personal Graph access tokens are opaque (not JWTs): no `tid`/`idp`.
    `/me` also omits `identities`. What *is* present on a live MSA `/me` is a
    non-GUID `id` (16-char alphanumeric). Work/school `/me.id` is an Entra UUID.

    Fail closed when neither JWT tenant nor `/me.id` is available, so a
    work/school account denied Sites.Read.All cannot slip through.
    """
    signals = microsoft_account_signals(token_data, me_profile)
    tid = str(signals.get("tid") or "").lower()
    if tid:
        return tid == MSA_CONSUMER_TENANT_ID
    idp = str(signals.get("idp") or "").lower()
    if "live.com" in idp or MSA_CONSUMER_TENANT_ID in idp:
        return True
    for issuer in signals.get("identity_issuers") or []:
        low = str(issuer).lower()
        if "live.com" in low or "microsoftaccount" in low:
            return True
    me_id = str(signals.get("me_id") or "")
    if me_id:
        return not bool(signals.get("me_id_is_guid"))
    return False


def missing_scopes_block_connect(
    token_data: Dict[str, Any],
    me_profile: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True if incomplete Graph consent should fail the Connect flow.

    Personal MSAs structurally cannot grant Sites.Read.All (no SharePoint
    Online). That single missing scope is allowed only when account-type
    evidence says MSA. A work/school tenant whose admin denied the same
    scope still fails.
    """
    missing = [str(s) for s in (token_data.get("_missing_scopes") or [])]
    if not missing:
        return False
    msa_onedrive_ok = (
        missing == ["Sites.Read.All"]
        and is_personal_microsoft_account(token_data, me_profile=me_profile)
    )
    return not msa_onedrive_ok


def _scope_key(scope: str) -> str:
    raw = (scope or "").strip()
    if "/" in raw:
        return raw.rsplit("/", 1)[-1]
    return raw

DEFAULT_SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Sites.Read.All",
    "https://graph.microsoft.com/Files.Read.All",
]
# Delegated GroupMember.Read.All is not requested: the live Azure app does not
# have it. Group ACEs fail closed (no expansion) rather than opening the file.


def _sharepoint_authority() -> str:
    # Delegated personal OAuth uses the v2 multi-tenant endpoint so any work
    # or personal Microsoft account can be offered the picker. Pinning
    # MICROSOFT_SHAREPOINT_TENANT_ID here caused AADSTS50020 for accounts
    # that are not members of that directory (e.g. Gmail MSA).
    # The Azure app registration MUST also allow those account types
    # (AzureADandPersonalMicrosoftAccount). /common does not override a
    # still-single-tenant app.
    return "https://login.microsoftonline.com/common/oauth2/v2.0"


def sharepoint_authorize_url() -> str:
    return f"{_sharepoint_authority()}/authorize"


def sharepoint_token_url() -> str:
    return f"{_sharepoint_authority()}/token"


class SharePointOAuthManager:
    def __init__(
        self,
        token_store,
        client_id: str,
        client_secret: str,
        scopes: Optional[List[str]] = None,
        principal_id: str = "",
        connection_scope: str = "personal",
    ):
        self.token_store = token_store
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes or list(DEFAULT_SCOPES)
        self.principal_id = principal_id
        self.connection_scope = connection_scope

    def _store_key(self, tenant_id: str) -> str:
        from app.connectors.sharepoint.keys import sharepoint_oauth_token_key

        return sharepoint_oauth_token_key(tenant_id, self.principal_id, self.connection_scope)

    def build_authorization_url(self, tenant_id: str, redirect_uri: str, state: str) -> str:
        del tenant_id
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(self.scopes),
            "state": state,
            "prompt": "select_account",
        }
        return f"{sharepoint_authorize_url()}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, tenant_id: str, code: str, redirect_uri: str) -> Dict[str, Any]:
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(sharepoint_token_url(), data=payload)
            if response.status_code >= 400:
                raise RuntimeError(f"SharePoint token exchange failed: {response.status_code}")
            data = response.json()
        requested = {_scope_key(s) for s in self.scopes}
        granted_raw = str(data.get("scope") or "")
        granted = {_scope_key(s) for s in granted_raw.split() if s}
        if data.get("refresh_token"):
            granted.add("offline_access")
        missing = sorted(requested - granted)
        extra = sorted(granted - requested)
        logger.info(
            "SharePoint token scopes requested=%s granted=%s missing=%s extra=%s",
            sorted(requested),
            sorted(granted),
            missing,
            extra,
        )
        data["_obtained_at"] = int(time.time())
        data["_requested_scopes"] = sorted(requested)
        data["_granted_scopes"] = sorted(granted)
        data["_missing_scopes"] = missing
        self.token_store.set_token(self._store_key(tenant_id), data)
        return data

    async def get_valid_token(self, tenant_id: str) -> str:
        blob = self.token_store.get_token(self._store_key(tenant_id)) or {}
        access = str(blob.get("access_token") or "")
        obtained = int(blob.get("_obtained_at") or 0)
        expires_in = int(blob.get("expires_in") or 3600)
        if access and obtained and (time.time() < obtained + expires_in - 120):
            return access
        refresh = str(blob.get("refresh_token") or "")
        if not refresh:
            if access:
                return access
            raise RuntimeError("SharePoint OAuth token missing — reconnect required")
        refreshed = await self._refresh(refresh)
        merged = dict(blob)
        merged.update(refreshed)
        merged["_obtained_at"] = int(time.time())
        self.token_store.set_token(self._store_key(tenant_id), merged)
        token = str(merged.get("access_token") or "")
        if not token:
            raise RuntimeError("SharePoint token refresh returned an empty access token")
        return token

    async def _refresh(self, refresh_token: str) -> Dict[str, Any]:
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": " ".join(self.scopes),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(sharepoint_token_url(), data=payload)
            if response.status_code >= 400:
                raise RuntimeError("SharePoint token refresh failed — re-authorize")
            return response.json()

    async def get_me_profile(self, access_token: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code >= 400:
                logger.warning("SharePoint GET /me failed status=%s", response.status_code)
                return {}
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def get_profile_email(self, access_token: str) -> str:
        data = await self.get_me_profile(access_token)
        return str(data.get("mail") or data.get("userPrincipalName") or "")


def sharepoint_oauth_from_settings(token_store, principal_id: str = "", connection_scope: str = "personal"):
    return SharePointOAuthManager(
        token_store,
        settings.microsoft_sharepoint_client_id or "",
        settings.microsoft_sharepoint_client_secret or "",
        principal_id=principal_id,
        connection_scope=connection_scope,
    )
