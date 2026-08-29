"""Provider plugin contract — keep connector-specific logic out of core router/tasks.

Add a future connector by:
1. Creating ``connectors/<name>/`` (oauth, services, webhooks, …)
2. Adding ``connectors/<name>/plugin.py`` that builds a ``ProviderPlugin``
3. One import/register line in ``provider_registry.py``

Core files should not grow large ``if google / elif microsoft / elif …`` trees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Sequence, Tuple


@dataclass
class BackfillAuth:
    """Auth objects needed by the shared backfill orchestrator."""

    token_store: Any
    oauth_manager: Any
    principal_id: str = ""
    mailbox_email: str = ""
    client_id: str = ""
    client_secret: str = ""
    allow_env_seed: bool = False


@dataclass
class ProviderPlugin:
    """One OAuth/webhook provider (may expose multiple source_types)."""

    provider_id: str
    sources: Tuple[str, ...]
    celery_queue: str = "connectors"
    # FastAPI APIRouter for inbound webhooks (optional)
    webhook_router: Any = None
    # Extra app routes: (path, endpoint, methods) e.g. legacy /outlook/callback
    legacy_routes: Tuple[Tuple[str, Any, Tuple[str, ...]], ...] = ()
    # Celery task name -> queue overrides (optional; defaults use celery_queue)
    celery_task_routes: Dict[str, str] = field(default_factory=dict)

    # --- HTTP / connection lifecycle ---
    build_authorize_url: Optional[Callable[..., Any]] = None
    handle_oauth_callback: Optional[Callable[..., Any]] = None
    has_token: Optional[Callable[[str, str], bool]] = None
    get_watch_info: Optional[Callable[..., Any]] = None
    on_disconnect: Optional[Callable[..., Any]] = None

    # --- Backfill / watches / incremental ---
    prepare_backfill: Optional[Callable[..., BackfillAuth]] = None
    register_watch: Optional[Callable[..., None]] = None
    process_notification: Optional[Callable[..., Dict[str, Any]]] = None

    def owns_source(self, source_type: str) -> bool:
        return source_type in self.sources
