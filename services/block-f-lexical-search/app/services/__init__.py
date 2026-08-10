"""Service package exports."""

from app.services.factory import get_lexical_store, reset_mock_store

__all__ = ["get_lexical_store", "reset_mock_store"]
