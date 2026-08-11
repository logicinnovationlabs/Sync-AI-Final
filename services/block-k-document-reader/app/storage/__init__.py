"""Storage package for Block D document access."""

from app.storage.document_store import DocumentStore, InMemoryDocumentStore

__all__ = ["DocumentStore", "InMemoryDocumentStore"]
