"""Block K: Document Reader Service - Core components."""

from app.services.document_reader.reader import (
    build_document_payload,
    read_document,
    redact_fields,
    stream_document_json,
)
from app.services.document_reader.store import DocumentStore, create_document_store
from app.services.document_reader.acl_checker import ACLChecker, create_acl_checker

__all__ = [
    "build_document_payload",
    "read_document",
    "redact_fields",
    "stream_document_json",
    "DocumentStore",
    "create_document_store",
    "ACLChecker",
    "create_acl_checker",
]
