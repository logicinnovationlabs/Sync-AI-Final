"""
Microsoft OAuth Manager - shared token acquisition/refresh for OneDrive + Outlook.

One tenant + one Microsoft account = one token with combined scopes.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import httpx
from urllib.parse import urlencode

from app.core.base_connector import TokenStore
from app.core.exceptions import UnauthorizedError
from app.connectors.microsoft.keys import microsoft_oauth_token_key

logger = logging.getLogger(__name__)

_DEFAULT_SCOPES = [
    "offline_access",
    "openid",
    "profile",
    "email",
    "User.Read",
    "Files.Read",
    "Files.Read.All",
    "Mail.Read",
]


class MicrosoftOAuthManager:
    """Manages OAuth tokens for Microsoft Graph services (OneDrive + Outlook)."""

    def __init__(
        self,
        token_store: TokenStore,
        client_id: str,
        client_secret: str,
        scopes: list[str],
        tenant: str = "common",
        principal_id: str = "",
    ):
        self.token_store = token_store
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes or list(_DEFAULT_SCOPES)
        self.tenant = (tenant or "common").strip() or "common"
        self.principal_id = str(principal_id or "").strip()

    @property
    def AUTH_ENDPOINT(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/authorize"

    @property
    def TOKEN_ENDPOINT(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/token"

    def build_authorization_url(self, tenant_id: str, redirect_uri: str, state: str = "") -> str:
        """Build OAuth authorization URL for the combined scope list."""
        _ = tenant_id
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "response_mode": "query",
            "scope": " ".join(self.scopes),
            "prompt": "consent",
        }
        if state:
            params["state"] = state
        return f"{self.AUTH_ENDPOINT}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self,
        tenant_id: str,
        code: str,
        redirect_uri: str,
    ) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_ENDPOINT,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "scope": " ".join(self.scopes),
                },
            )

            if response.status_code != 200:
                raise UnauthorizedError(f"Token exchange failed: {response.text}")

            token_data = response.json()
            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = (
                datetime.utcnow() + timedelta(seconds=expires_in)
            ).isoformat()

            token_key = self._get_token_key(tenant_id)
            self.token_store.set_token(token_key, token_data)
            return token_data

    async def get_valid_token(self, tenant_id: str) -> str:
        """Get a valid access token, refreshing if necessary."""
        token_key = self._get_token_key(tenant_id)
        token_data = self.token_store.get_token(token_key)
        if not token_data and self.principal_id:
            token_data = self.token_store.get_token(microsoft_oauth_token_key(tenant_id))

        if not token_data:
            raise UnauthorizedError(
                f"No Microsoft OAuth tokens found for tenant {tenant_id}. "
                "User must complete OAuth flow."
            )

        expires_at_str = token_data.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.utcnow() >= expires_at - timedelta(minutes=5):
                token_data = await self._refresh_token(tenant_id, token_data)

        return token_data["access_token"]

    async def _refresh_token(self, tenant_id: str, token_data: Dict[str, Any]) -> Dict[str, Any]:
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            raise UnauthorizedError(
                f"No refresh token available for tenant {tenant_id}. "
                "User must re-authorize."
            )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_ENDPOINT,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "scope": " ".join(self.scopes),
                },
            )

            if response.status_code != 200:
                try:
                    from app.connectors.google.status_store import set_status

                    set_status(
                        tenant_id,
                        "onedrive",
                        user_id=self.principal_id,
                        connection_status="needs_reauth",
                        last_error="token_refresh_failed",
                    )
                    set_status(
                        tenant_id,
                        "outlook",
                        user_id=self.principal_id,
                        connection_status="needs_reauth",
                        last_error="token_refresh_failed",
                    )
                except Exception:
                    pass
                raise UnauthorizedError(
                    f"Token refresh failed for tenant {tenant_id}: {response.text}"
                )

            new_token_data = response.json()
            expires_in = new_token_data.get("expires_in", 3600)
            new_token_data["expires_at"] = (
                datetime.utcnow() + timedelta(seconds=expires_in)
            ).isoformat()

            if "refresh_token" not in new_token_data:
                new_token_data["refresh_token"] = refresh_token

            token_key = self._get_token_key(tenant_id)
            self.token_store.set_token(token_key, new_token_data)
            return new_token_data

    def _get_token_key(self, tenant_id: str) -> str:
        return microsoft_oauth_token_key(tenant_id, self.principal_id)


def microsoft_oauth_from_settings(
    token_store: TokenStore, principal_id: str = ""
) -> "MicrosoftOAuthManager":
    """Build a MicrosoftOAuthManager from app settings + manifest scopes."""
    from app.core.config import settings

    return MicrosoftOAuthManager(
        token_store,
        settings.microsoft_client_id or "",
        settings.microsoft_client_secret or "",
        list(_DEFAULT_SCOPES),
        tenant=getattr(settings, "microsoft_tenant", None) or "common",
        principal_id=principal_id,
    )
