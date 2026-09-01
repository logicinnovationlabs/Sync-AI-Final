"""
Diagnostic endpoint for checking environment configuration.
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any

from app.core.config import settings
from app.api.deps import get_current_user

router = APIRouter()


@router.get("/env-check", response_model=Dict[str, Any])
async def check_environment(
    current_user = Depends(get_current_user)
):
    """
    Check critical environment variable configurations (non-sensitive values only).
    """
    return {
        "opensearch": {
            "enabled": settings.lexical_enabled,
            "resolved_url": settings.resolved_lexical_url or "NOT SET",
            "opensearch_host": settings.opensearch_host,
            "opensearch_port": settings.opensearch_port,
            "opensearch_index_prefix": settings.opensearch_index_prefix,
        },
        "qdrant": {
            "url_configured": bool(settings.qdrant_url),
            "qdrant_url": settings.qdrant_url if settings.qdrant_url else "NOT SET",
            "qdrant_host": settings.qdrant_host,
            "qdrant_port": settings.qdrant_port,
        },
        "lexical_search": {
            "enabled": settings.lexical_enabled,
            "lexical_search_url": getattr(settings, "lexical_search_url", None),
        },
        "embedding": {
            "provider": settings.embedding_provider,
            "model": settings.embedding_model,
            "dimensions": settings.embedding_dimensions,
        },
    }
