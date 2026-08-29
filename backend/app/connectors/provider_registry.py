"""Central registry of connector provider plugins.

To add WhatsApp/Jira/Tally later: create ``connectors/<name>/plugin.py`` and
add one import + ``register(plugin)`` below. Core router/tasks should not grow.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

from app.connectors.plugin_base import ProviderPlugin

logger = logging.getLogger(__name__)

_BY_PROVIDER: Dict[str, ProviderPlugin] = {}
_BY_SOURCE: Dict[str, ProviderPlugin] = {}


def register(plugin: ProviderPlugin) -> None:
    _BY_PROVIDER[plugin.provider_id] = plugin
    for source in plugin.sources:
        _BY_SOURCE[source] = plugin
    logger.info(
        "Registered connector provider=%s sources=%s",
        plugin.provider_id,
        ",".join(plugin.sources),
    )


def get(provider_id: str) -> Optional[ProviderPlugin]:
    return _BY_PROVIDER.get(provider_id)


def get_by_source(source_type: str) -> Optional[ProviderPlugin]:
    return _BY_SOURCE.get(source_type)


def all_plugins() -> List[ProviderPlugin]:
    return list(_BY_PROVIDER.values())


def celery_task_routes() -> Dict[str, dict]:
    """Merge per-plugin Celery routes for celery_app.conf.task_routes."""
    routes: Dict[str, dict] = {}
    for plugin in all_plugins():
        for task_name, queue in (plugin.celery_task_routes or {}).items():
            routes[task_name] = {"queue": queue}
        # Generic notification task can land on the plugin queue when routed by name;
        # also keep a default for process_connector_notification per first MS plugin.
    return routes


def load_builtin_plugins() -> None:
    """Import-and-register built-in providers. One line per future connector."""
    if _BY_PROVIDER:
        return
    from app.connectors.google.plugin import plugin as google_plugin
    from app.connectors.microsoft.plugin import plugin as microsoft_plugin

    register(google_plugin)
    register(microsoft_plugin)


# Eager load so router/tasks/main always see providers.
load_builtin_plugins()
