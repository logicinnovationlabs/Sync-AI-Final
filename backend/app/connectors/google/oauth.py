"""
Google OAuth Manager - shared token acquisition/refresh for all Google services.

This module owns OAuth token management for every service under app/connectors/google/.
Both DriveConnector and GmailConnector (and any future Google service) call into this —
none implement their own refresh logic.

One tenant + one Google account = one token with combined scopes.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import httpx
from urllib.parse import urlencode

from app.core.base_connector import TokenStore
from app.core.exceptions import UnauthorizedError

logger = logging.getLogger(__name__)


class GoogleOAuthManager:
    """
    Manages OAuth tokens for all Google Workspace services.
    
    Implements token refresh, expiry checking, and authorization URL generation
    for the combined scope list in manifest.yaml.
    """
    
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    
    def __init__(
        self,
        token_store: TokenStore,
        client_id: str,
        client_secret: str,
        scopes: list[str],
    ):
        """
        Initialize OAuth manager.
        
        Args:
            token_store: Secure token storage
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
            scopes: List of OAuth scopes (from manifest.yaml)
        """
        self.token_store = token_store
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes
    
    def build_authorization_url(self, tenant_id: str, redirect_uri: str, state: str = "") -> str:
        """
        Build OAuth authorization URL for the combined scope list.
        
        This requests ALL scopes in manifest.yaml in one consent screen.
        
        Args:
            tenant_id: Tenant identifier
            redirect_uri: OAuth callback URL
            state: Optional state parameter for CSRF protection
            
        Returns:
            Authorization URL string
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",       # Force consent screen to get refresh token
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
        """
        Exchange authorization code for access and refresh tokens.
        
        Args:
            tenant_id: Tenant identifier
            code: Authorization code from OAuth callback
            redirect_uri: OAuth callback URL (must match authorization request)
            
        Returns:
            Token data dict with access_token, refresh_token, expires_in, etc.
            
        Raises:
            UnauthorizedError if token exchange fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_ENDPOINT,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            
            if response.status_code != 200:
                raise UnauthorizedError(f"Token exchange failed: {response.text}")
            
            token_data = response.json()
            
            # Calculate expiration timestamp
            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = (
                datetime.utcnow() + timedelta(seconds=expires_in)
            ).isoformat()
            
            # Store tokens
            token_key = self._get_token_key(tenant_id)
            self.token_store.set_token(token_key, token_data)
            
            return token_data
    
    async def get_valid_token(self, tenant_id: str) -> str:
        """
        Get a valid access token, refreshing if necessary.
        
        This is the main entry point for all Google connectors.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Valid access token string
            
        Raises:
            UnauthorizedError if no tokens stored or refresh fails
        """
        token_key = self._get_token_key(tenant_id)
        token_data = self.token_store.get_token(token_key)
        
        if not token_data:
            raise UnauthorizedError(
                f"No Google OAuth tokens found for tenant {tenant_id}. "
                "User must complete OAuth flow."
            )
        
        # Check if token is expired or will expire soon (5 minute buffer)
        expires_at_str = token_data.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.utcnow() >= expires_at - timedelta(minutes=5):
                # Token expired or expiring soon, refresh it
                token_data = await self._refresh_token(tenant_id, token_data)
        
        return token_data["access_token"]
    
    async def _refresh_token(self, tenant_id: str, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Refresh an expired access token using the refresh token.
        
        Args:
            tenant_id: Tenant identifier
            token_data: Current token data with refresh_token
            
        Returns:
            Updated token data
            
        Raises:
            UnauthorizedError if refresh fails
        """
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
                },
            )
            
            if response.status_code != 200:
                try:
                    from app.connectors.google.status_store import set_status

                    set_status(
                        tenant_id,
                        "google_drive",
                        connection_status="needs_reauth",
                        last_error="token_refresh_failed",
                    )
                    set_status(
                        tenant_id,
                        "google_gmail",
                        connection_status="needs_reauth",
                        last_error="token_refresh_failed",
                    )
                except Exception:
                    pass
                raise UnauthorizedError(
                    f"Token refresh failed for tenant {tenant_id}: {response.text}"
                )
            
            new_token_data = response.json()
            
            # Calculate new expiration
            expires_in = new_token_data.get("expires_in", 3600)
            new_token_data["expires_at"] = (
                datetime.utcnow() + timedelta(seconds=expires_in)
            ).isoformat()
            
            # Preserve refresh token if not returned (Google sometimes omits it)
            if "refresh_token" not in new_token_data:
                new_token_data["refresh_token"] = refresh_token
            
            # Update stored tokens
            token_key = self._get_token_key(tenant_id)
            self.token_store.set_token(token_key, new_token_data)
            
            return new_token_data
    
    def _get_token_key(self, tenant_id: str) -> str:
        """Generate token storage key for a tenant."""
        return f"google_oauth:{tenant_id}"


def seed_token_store_from_env(
    token_store: TokenStore,
    tenant_id: str,
    *,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    refresh_token: Optional[str] = None,
) -> bool:
    """
    Seed TokenStore with Google OAuth tokens from env/settings when present.

    Block B's connectors read credentials from TokenStore under key
    ``google_oauth:{tenant_id}`` (see GoogleOAuthManager._get_token_key).
    Celery tasks historically created an empty DummyTokenStore; this helper
    fills it from GOOGLE_REFRESH_TOKEN (+ optional client fields) so real
    Drive/Gmail crawls can authenticate without a separate DB vault row.

    Returns True if a refresh token was seeded; False if nothing to seed.
    Never logs the refresh token value.
    """
    rt = refresh_token
    if not rt:
        from app.storage.vault_client import PlatformSecretKeys, vault_client

        rt = vault_client.get(PlatformSecretKeys.GOOGLE_REFRESH_TOKEN) or ""
    rt = (rt or "").strip()
    if not rt:
        return False

    existing = token_store.get_token(f"google_oauth:{tenant_id}") or {}
    if existing.get("refresh_token") or existing.get("access_token"):
        logger.info(
            "seed_token_store_from_env: skip, token already stored for tenant (will not clobber)"
        )
        return False

    # Expire access immediately so get_valid_token() refreshes on first use.
    token_store.set_token(
        f"google_oauth:{tenant_id}",
        {
            "access_token": "pending_refresh",
            "refresh_token": rt,
            "expires_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "token_type": "Bearer",
        },
    )
    return True


def google_oauth_from_settings(token_store: TokenStore) -> "GoogleOAuthManager":
    """Build a GoogleOAuthManager from app settings + manifest scopes."""
    from app.core.config import settings

    client_id = settings.google_client_id or ""
    client_secret = settings.google_client_secret or ""
    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
    ]
    return GoogleOAuthManager(token_store, client_id, client_secret, scopes)

