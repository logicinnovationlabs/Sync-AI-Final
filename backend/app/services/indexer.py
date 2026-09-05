"""
Blind Indexer: accepts UnifiedDocument, allowlists metadata, generates embeddings, indexes to Qdrant.

Phase 1 parity (critical for answer quality):
- Each chunk gets its **own** embedding (never reuse the document vector)
- Document embeddings use ``retrieval_document`` task type
- Chunk size ~1000 chars with overlap (Phase 1 used ~1000 tokens; chars are a close stand-in)
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.core.base_connector import UnifiedDocument
from app.core.config import settings
from app.services.embedding import embedding_service
from app.services.registry import connector_registry
from app.storage.qdrant_client import qdrant_client

logger = logging.getLogger(__name__)


class Indexer:
    """Blind indexer — never imports specific connectors by name."""

    def __init__(self) -> None:
        self.registry = connector_registry
        self.embedding_service = embedding_service
        self.qdrant = qdrant_client
        try:
            dimension = self.embedding_service.get_dimension()
            self.qdrant.ensure_collection(dimension)
        except Exception as e:
            logger.warning("Could not initialize Qdrant collection: %s", e)

    async def bulk_index(
        self,
        documents: List[UnifiedDocument],
        tenant_id: str,
        extra_acl: Optional[List[str]] = None,
    ) -> None:
        if not documents:
            return

        logger.info("Indexing %s documents for tenant %s", len(documents), tenant_id)

        processed_docs = []
        for doc in documents:
            allowed_keys = self.registry.get_allowed_metadata_keys(doc.source_type)
            filtered_metadata = {
                k: v
                for k, v in doc.structured_metadata.items()
                if k in allowed_keys
            }
            processed_docs.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "content": doc.content or "",
                    "source_type": doc.source_type,
                    "url": doc.url,
                    "permissions": index_acl_terms(doc.permissions, extra_acl),
                    "created_at": doc.created_at.isoformat(),
                    "updated_at": doc.updated_at.isoformat(),
                    "source_updated_at": doc.source_updated_at.isoformat(),
                    "structured_metadata": filtered_metadata,
                    "tenant_id": tenant_id,
                }
            )

        # Document-level vectors for the Block B `documents` collection.
        texts = [f"{doc['title']} {doc['content']}"[:12000] for doc in processed_docs]
        vectors = await self.embedding_service.embed_documents(texts)

        qdrant_docs = []
        for doc in processed_docs:
            payload = dict(doc)
            body = payload.get("content") or ""
            if len(body) > 8000:
                payload["content"] = body[:8000]
            qdrant_docs.append(payload)

        await self.qdrant.upsert_documents(qdrant_docs, vectors)
        await self._fanout_search_pipeline(processed_docs, tenant_id, extra_acl or [])
        logger.info(
            "Successfully indexed %s documents for tenant %s",
            len(documents),
            tenant_id,
        )

    async def _fanout_search_pipeline(
        self,
        processed_docs: List[dict],
        tenant_id: str,
        extra_acl: List[str],
    ) -> None:
        """Chunk + lexical + **per-chunk** vector + document store."""
        from app.services.chunking.prose import ProseChunker
        from app.services.ingest.local_index import local_ingest_index

        # Phase 1 used ~1000 tokens / 200 overlap. Char approx keeps passages usable.
        chunk_size = int(getattr(settings, "chunk_size", None) or 1000)
        chunk_overlap = int(getattr(settings, "chunk_overlap", None) or 200)
        chunker = ProseChunker(chunk_size=chunk_size, overlap=chunk_overlap)
        model_version = (
            getattr(settings, "embedding_model_version", None)
            or getattr(settings, "model_version", None)
            or "default"
        )

        lexical_docs = []
        pending_chunks: List[dict] = []
        chunk_embed_texts: List[str] = []

        for doc in processed_docs:
            doc_id = str(doc["id"])
            acl_terms = index_acl_terms(doc.get("permissions"), extra_acl)
            body = doc.get("content") or ""
            title = doc.get("title") or ""
            local_ingest_index.upsert(
                tenant_id,
                {
                    "document_id": doc_id,
                    "title": title,
                    "body_text": body,
                    "content": body,
                    "acl_terms": acl_terms,
                    "source": doc.get("source_type"),
                },
            )
            lexical_docs.append(
                {
                    "document_id": doc_id,
                    "title": title,
                    "body_text": body,
                    "source": doc.get("source_type"),
                    "acl_filter_terms": acl_terms,
                    "deleted": False,
                }
            )
            pieces = chunker.chunk_with_parent(
                f"{title}\n{body}", parent_doc_id=doc_id
            ) or [
                {
                    "id": "0",
                    "content": f"{title}\n{body}"[:2000],
                    "parent_doc_id": doc_id,
                }
            ]
            if str(doc.get("source_type") or "") == "sharepoint":
                first = str((pieces[0] or {}).get("content") or "") if pieces else ""
                logger.info(
                    "SharePoint chunked doc_id=%s n_chunks=%s first_len=%s first_bounds=0:%s",
                    doc_id,
                    len(pieces),
                    len(first),
                    len(first),
                )
            meta_extra = {
                k: v
                for k, v in (doc.get("structured_metadata") or {}).items()
                if k in ("from_email", "to_emails", "subject", "thread_id")
                and v not in (None, "", [])
            }
            for piece in pieces:
                chunk_body = str(piece.get("content") or "")
                # Phase 1 embeds the chunk text itself (optionally with title).
                chunk_embed_texts.append(f"{title}\n{chunk_body}"[:8000])
                pending_chunks.append(
                    {
                        "chunk_id": f"{doc_id}:{piece.get('id') or '0'}",
                        "document_id": doc_id,
                        "model_version": str(model_version),
                        "acl_terms": acl_terms,
                        "chunk_text": chunk_body,
                        "metadata": {
                            "source_type": doc.get("source_type"),
                            "title": title,
                            "parent_doc_id": piece.get("parent_doc_id") or doc_id,
                            **meta_extra,
                        },
                    }
                )
            try:
                from app.services.document_reader.store import get_shared_document_store

                store = get_shared_document_store()
                if hasattr(store, "upsert"):
                    await store.upsert(
                        tenant_id,
                        doc_id,
                        title=title,
                        body=body,
                        structured_metadata=doc.get("structured_metadata") or {},
                        owner_principal_id=next(
                            (
                                p.split(":", 1)[-1]
                                for p in acl_terms
                                if ":" in str(p)
                            ),
                            "",
                        ),
                        created_at=doc.get("created_at"),
                        updated_at=doc.get("updated_at"),
                        acl_entries=acl_terms,
                    )
            except Exception:
                logger.warning(
                    "document store upsert failed id=%s", doc_id, exc_info=True
                )

        try:
            from app.services.lexical.opensearch_store import OpenSearchLexicalStore

            await OpenSearchLexicalStore().index_batch(tenant_id, lexical_docs)
        except Exception:
            logger.warning("lexical index fan-out skipped", exc_info=True)

        if not pending_chunks:
            return

        try:
            # ROOT FIX vs dumb Phase 2 answers: embed EACH chunk, not the whole doc once.
            chunk_vectors = await self.embedding_service.embed_documents(
                chunk_embed_texts
            )
            vector_chunks = []
            for meta, vec in zip(pending_chunks, chunk_vectors):
                row = dict(meta)
                row["embedding"] = vec
                vector_chunks.append(row)
            from app.services.vector.qdrant_store import QdrantVectorStore

            await QdrantVectorStore().upsert_batch(tenant_id, vector_chunks)
            provider_name = type(getattr(self.embedding_service, "provider", None)).__name__
            first_vec = vector_chunks[0].get("embedding") if vector_chunks else None
            sharepoint_n = sum(
                1
                for row in vector_chunks
                if str((row.get("metadata") or {}).get("source_type") or "") == "sharepoint"
            )
            logger.info(
                "Upserted %s chunk vectors tenant=%s provider=%s dim=%s sharepoint_chunks=%s sample_chunk_id=%s",
                len(vector_chunks),
                tenant_id,
                provider_name,
                len(first_vec) if isinstance(first_vec, list) else 0,
                sharepoint_n,
                (vector_chunks[0].get("chunk_id") if vector_chunks else None),
            )
        except Exception:
            logger.warning("vector index fan-out skipped", exc_info=True)

    async def delete_by_ids(
        self,
        document_ids: List[str],
        tenant_id: str,
        source_type: str,
    ) -> None:
        if not document_ids:
            return
        logger.info(
            "Deleting %s documents from %s for tenant %s",
            len(document_ids),
            source_type,
            tenant_id,
        )
        
        await self.qdrant.delete_by_ids(document_ids, tenant_id=tenant_id)
        await self._delete_canonical_acls(document_ids, tenant_id)

    async def _delete_canonical_acls(
        self,
        document_ids: List[str],
        tenant_id: str,
    ) -> None:
        """Drop matching canonical_documents and acl_entries (fail closed on routing)."""
        from uuid import UUID

        from app.core.exceptions import TenantNotFoundError
        from app.services.tenant_resolver import tenant_resolver
        from app.storage.canonical_repo import CanonicalRepo
        from app.storage.tenant_db import tenant_db_manager

        try:
            tenant_uuid = UUID(str(tenant_id))
        except (TypeError, ValueError):
            logger.error("delete ACL skipped: invalid tenant_id")
            return

        try:
            routing = await tenant_resolver.resolve(str(tenant_id))
        except TenantNotFoundError:
            logger.error("delete ACL tenant not found tenant_id=%s", tenant_id)
            return
        except Exception:
            logger.exception("delete ACL routing failed tenant_id=%s", tenant_id)
            raise

        factory = tenant_db_manager.get_session_factory(
            routing.db_host,
            routing.db_name,
            routing.db_user,
            routing.db_password,
            str(routing.tenant_id),
        )
        session = factory()
        try:
            repo = CanonicalRepo(use_memory=False, session=session)
            await repo.delete_documents_and_acls(document_ids, tenant_uuid)
        finally:
            await session.close()
        
    async def reindex_by_ids(
        self,
        tenant_id: str,
        document_ids: List[str],
        repo,
    ) -> None:
        """Rebuild UnifiedDocuments for ``document_ids`` and call ``bulk_index``.

        ``bulk_index`` cannot accept an id list; this is the minimal scoped wrapper.
        """
        if not document_ids:
            return
        from app.core.base_connector import UnifiedDocument

        documents = []
        for document_id in document_ids:
            doc = await repo.get_document(document_id)
            if doc is None:
                logger.warning("reindex skipped missing document_id=%s", document_id)
                continue
            entries = await repo.get_acl_entries(document_id)
            permissions = []
            for entry in entries:
                if entry.principal_id:
                    permissions.append(f"user:{entry.principal_id}")
                elif entry.group_id:
                    permissions.append(f"group:{entry.group_id}")
            documents.append(
                UnifiedDocument(
                    id=doc.source_id,
                    title=doc.title,
                    content=doc.content,
                    source_type=doc.source_type,
                    url=doc.url,
                    permissions=list(set(permissions)),
                    created_at=doc.created_at,
                    updated_at=doc.updated_at,
                    source_updated_at=doc.source_updated_at,
                    structured_metadata=doc.structured_metadata or {},
                )
            )
        if documents:
            await self.bulk_index(documents, tenant_id)


indexer = Indexer()


def index_acl_terms(
    permissions: Optional[List[str]], extra_acl: Optional[List[str]] = None
) -> List[str]:
    """Merge mirrored document ACL with connector-owner extra_acl.

    extra_acl is additive so the connecting admin can search. It must not
    replace Graph/Drive-compiled permissions or members on the source ACL
    disappear from OpenSearch/Qdrant.
    """
    return _acl_terms(list(permissions or []), extra_acl)


def _acl_terms(
    permissions: List[str], extra_acl: Optional[List[str]] = None
) -> List[str]:
    terms = []
    seen = set()
    for raw in list(permissions or []) + list(extra_acl or []):
        value = str(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        terms.append(value)
        if value.startswith("user:") or value.startswith("group:"):
            bare = value.split(":", 1)[-1]
            if bare and bare not in seen:
                seen.add(bare)
                terms.append(bare)
    return terms
