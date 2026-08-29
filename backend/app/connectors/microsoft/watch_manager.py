"""Microsoft Graph subscription registration (webhook push, not polling)."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any, Dict

from app.connectors.microsoft.clients.graph_client import GraphClient
from app.connectors.microsoft.oauth import MicrosoftOAuthManager

logger = logging.getLogger(__name__)


class MicrosoftWatchManager:
    """Creates Graph change-notification subscriptions after first backfill."""

    SUBSCRIPTION_MINUTES = 4000  # Graph max ~4230 minutes

    def __init__(self, oauth_manager: MicrosoftOAuthManager, cursor_store, webhook_base_url: str):
        self.oauth_manager = oauth_manager
        self.cursor_store = cursor_store
        self.webhook_base_url = webhook_base_url.rstrip("/")
        self.graph = GraphClient()

    async def register_onedrive_subscription(
        self, tenant_id: str, *, user_id: str = ""
    ) -> Dict[str, Any]:
        return await self._register(
            tenant_id,
            source_type="onedrive",
            resource="/me/drive/root",
            user_id=user_id,
        )

    async def register_outlook_subscription(
        self, tenant_id: str, *, user_id: str = ""
    ) -> Dict[str, Any]:
        return await self._register(
            tenant_id,
            source_type="outlook",
            resource="me/mailFolders('inbox')/messages",
            user_id=user_id,
        )

    async def _register(
        self,
        tenant_id: str,
        *,
        source_type: str,
        resource: str,
        user_id: str = "",
    ) -> Dict[str, Any]:
        token = await self.oauth_manager.get_valid_token(tenant_id)
        client_state = f"{tenant_id}|{user_id}|{secrets.token_urlsafe(16)}"
        notification_url = f"{self.webhook_base_url}/webhooks/microsoft/graph"
        response = await self.graph.create_subscription(
            token,
            resource=resource,
            notification_url=notification_url,
            client_state=client_state,
            minutes=self.SUBSCRIPTION_MINUTES,
        )
        expiration = response.get("expirationDateTime") or ""
        expiration_ms = 0
        try:
            expiration_ms = int(
                datetime.fromisoformat(expiration.replace("Z", "+00:00")).timestamp() * 1000
            )
        except Exception:
            expiration_ms = 0

        scope_id = f"{tenant_id}:{user_id}" if user_id else tenant_id
        watch_data = {
            "channel_id": response.get("id"),
            "resource_id": source_type,
            "subscription_id": response.get("id"),
            "client_state": client_state,
            "expiration": expiration_ms,
            "expirationDateTime": expiration,
            "resource": resource,
            "user_id": user_id,
            "tenant_id": tenant_id,
        }
        await self.cursor_store.set_watch_info(scope_id, source_type, watch_data)
        logger.info(
            "Registered Graph subscription source=%s tenant=%s id=%s",
            source_type,
            tenant_id,
            response.get("id"),
        )
        return response

    async def delete_subscription(
        self, tenant_id: str, source_type: str, *, user_id: str = ""
    ) -> None:
        scope_id = f"{tenant_id}:{user_id}" if user_id else tenant_id
        watch = await self.cursor_store.get_watch_info(scope_id, source_type)
        if not watch:
            return
        sub_id = watch.get("subscription_id") or watch.get("channel_id")
        if not sub_id:
            return
        try:
            token = await self.oauth_manager.get_valid_token(tenant_id)
            await self.graph.delete_subscription(token, str(sub_id))
        except Exception as exc:
            logger.warning(
                "Failed to delete Graph subscription %s: %s", sub_id, type(exc).__name__
            )
