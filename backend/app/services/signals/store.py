"""Abstract activity / signal store interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.models.activity import (
    ActivityConfig,
    ActivityEvent,
    DocumentSignalResponse,
    PurgeResult,
    StoredEvent,
    UserSignalResponse,
)


class ActivityStore(ABC):
    """Tenant-isolated activity event store + signal aggregates."""

    @abstractmethod
    async def health(self) -> Tuple[bool, str]:
        ...

    @abstractmethod
    async def ensure_tenant(self, tenant_id: str, config: Optional[ActivityConfig] = None) -> None:
        ...

    @abstractmethod
    async def get_config(self, tenant_id: str) -> ActivityConfig:
        ...

    @abstractmethod
    async def set_config(self, config: ActivityConfig) -> None:
        ...

    @abstractmethod
    async def ingest_event(
        self,
        tenant_id: str,
        event: ActivityEvent,
        *,
        ingested_at: Optional[datetime] = None,
    ) -> str:
        """
        Persist a single event.

        Returns: "ingested" | "already_processed"
        """

    @abstractmethod
    async def get_event(self, tenant_id: str, event_id: str) -> Optional[StoredEvent]:
        ...

    @abstractmethod
    async def list_events(
        self,
        tenant_id: str,
        *,
        object_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        include_expired: bool = True,
    ) -> List[StoredEvent]:
        ...

    @abstractmethod
    async def get_user_signals(self, tenant_id: str, user_id: str) -> UserSignalResponse:
        ...

    @abstractmethod
    async def get_document_signals(
        self, tenant_id: str, document_id: str
    ) -> DocumentSignalResponse:
        ...

    @abstractmethod
    async def purge_expired(self, *, now: Optional[datetime] = None) -> PurgeResult:
        ...

    @abstractmethod
    async def clear_tenant(self, tenant_id: str) -> None:
        ...

    @abstractmethod
    async def recompute_signals(self, tenant_id: str) -> None:
        """Rebuild user + document aggregates from raw events (recovery path)."""

    async def metrics_snapshot(self) -> Dict[str, Any]:
        return {}
