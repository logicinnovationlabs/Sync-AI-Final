"""Graph writer: consume ingest.canonical.v1 events into the knowledge graph."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.services.factory import get_graph_store

logger = logging.getLogger(__name__)

# Map content_type / object_type → Neo4j label
_CONTENT_LABELS = {
    "document": "Document",
    "doc": "Document",
    "message": "Message",
    "email": "Message",
    "ticket": "Ticket",
    "issue": "Ticket",
    "code": "CodeFile",
    "codefile": "CodeFile",
    "file": "CodeFile",
    "repository": "Repository",
    "repo": "Repository",
    "folder": "Folder",
    "team": "Team",
    "project": "Project",
    "topic": "Topic",
}


def _label_for_content(payload: Dict[str, Any]) -> str:
    raw = (
        payload.get("object_type")
        or payload.get("content_type")
        or payload.get("type")
        or "document"
    )
    return _CONTENT_LABELS.get(str(raw).lower(), "Document")


class GraphWriter:
    """
    Process ingest.canonical.v1 envelopes into nodes + relationships.

    Idempotent via MERGE semantics and updated_at stale-write checks.
    """

    def __init__(self, store=None) -> None:
        self.store = store or get_graph_store()

    async def process_event(self, event: Dict[str, Any]) -> Optional[str]:
        """
        Accept envelope:
          { "tenant_id": "...", "event_type": "DocumentCreated", "payload": {...} }
        or flat canonical document with tenant_id.
        """
        tenant_id = event.get("tenant_id")
        payload = event.get("payload") or event
        if not tenant_id:
            tenant_id = payload.get("tenant_id")
        event_type = (
            event.get("event_type")
            or event.get("type")
            or payload.get("event_type")
            or "DocumentCreated"
        )
        if not tenant_id:
            logger.error("canonical event missing tenant_id: %s", event)
            return None

        tenant_id = str(tenant_id)
        await self.store.ensure_tenant(tenant_id)

        handlers = {
            "DocumentCreated": self._handle_document,
            "DocumentUpdated": self._handle_document,
            "PrincipalCreated": self._handle_principal,
            "PrincipalUpdated": self._handle_principal,
            "GroupCreated": self._handle_group,
            "GroupUpdated": self._handle_group,
            "ACLChanged": self._handle_acl,
            "PersonCreated": self._handle_principal,
            "ActivityViewed": self._handle_activity_viewed,
            "ActivityCommented": self._handle_activity_commented,
        }
        handler = handlers.get(event_type, self._handle_document)
        return await handler(tenant_id, payload, event_type)

    async def _handle_document(
        self, tenant_id: str, payload: Dict[str, Any], event_type: str
    ) -> Optional[str]:
        doc_id = payload.get("document_id") or payload.get("source_id") or payload.get("id")
        if not doc_id:
            logger.error("document event missing id: %s", payload)
            return None
        doc_id = str(doc_id)
        deleted = bool(payload.get("deleted") or payload.get("is_deleted"))
        if deleted:
            await self.store.delete_node(tenant_id, doc_id)
            return doc_id

        label = _label_for_content(payload)
        meta = payload.get("structured_metadata") or payload.get("metadata") or {}
        props = {
            "title": payload.get("title") or meta.get("title"),
            "body_text": payload.get("body_text") or payload.get("content"),
            "source": payload.get("source") or meta.get("source"),
            "created_at": payload.get("created_at") or meta.get("created_at"),
            "updated_at": payload.get("updated_at") or meta.get("updated_at"),
            "visibility_mode": payload.get("visibility_mode") or meta.get("visibility_mode"),
        }
        await self.store.upsert_node(tenant_id, label, doc_id, props)

        owner = (
            payload.get("owner_principal_id")
            or payload.get("owner")
            or meta.get("owner_principal_id")
            or meta.get("owner")
        )
        if owner:
            owner = str(owner)
            await self.store.upsert_node(
                tenant_id, "Person", owner, {"display_name": owner}
            )
            # (Document)-[:OWNS]->(Person) per master prompt AND authorship
            await self.store.upsert_edge(
                tenant_id,
                "OWNS",
                doc_id,
                owner,
                source_label=label,
                target_label="Person",
            )
            await self.store.upsert_edge(
                tenant_id,
                "AUTHORED",
                owner,
                doc_id,
                source_label="Person",
                target_label=label,
            )

        # References / linked docs
        for ref in payload.get("references") or meta.get("references") or []:
            ref_id = str(ref.get("id") if isinstance(ref, dict) else ref)
            await self.store.upsert_edge(
                tenant_id,
                "REFERENCES",
                doc_id,
                ref_id,
                source_label=label,
                target_label="Document",
            )
        for linked in payload.get("linked_to") or meta.get("linked_to") or []:
            lid = str(linked.get("id") if isinstance(linked, dict) else linked)
            await self.store.upsert_edge(
                tenant_id,
                "LINKED_TO",
                doc_id,
                lid,
                source_label=label,
                target_label="Document",
            )

        # Shared-with principals/groups from ACL
        for share in payload.get("shared_with") or meta.get("shared_with") or []:
            if isinstance(share, dict):
                sid = str(share.get("id") or share.get("principal_id"))
                stype = share.get("type") or "Person"
            else:
                sid, stype = str(share), "Person"
            tgt_label = "Group" if str(stype).lower() == "group" else "Person"
            # Need a sharer — use owner if present
            if owner:
                await self.store.upsert_edge(
                    tenant_id,
                    "SHARED_WITH",
                    str(owner),
                    sid,
                    source_label="Person",
                    target_label=tgt_label,
                )

        logger.info("Graph upserted doc=%s tenant=%s type=%s", doc_id, tenant_id, event_type)
        return doc_id

    async def _handle_principal(
        self, tenant_id: str, payload: Dict[str, Any], event_type: str
    ) -> Optional[str]:
        pid = (
            payload.get("principal_id")
            or payload.get("source_id")
            or payload.get("external_id")
            or payload.get("id")
            or payload.get("email")
        )
        if not pid:
            logger.error("principal event missing id: %s", payload)
            return None
        pid = str(pid)
        props = {
            "display_name": payload.get("display_name") or payload.get("name"),
            "email": payload.get("email"),
            "title": payload.get("title"),
            "department": payload.get("department"),
            "team": payload.get("team"),
            "aliases": list(payload.get("aliases") or []),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }
        await self.store.upsert_node(tenant_id, "Person", pid, props)

        manager = payload.get("manager_id") or payload.get("reports_to")
        if manager:
            await self.store.upsert_edge(
                tenant_id,
                "REPORTS_TO",
                pid,
                str(manager),
                source_label="Person",
                target_label="Person",
            )

        for gid in payload.get("group_ids") or payload.get("groups") or []:
            gid = str(gid.get("id") if isinstance(gid, dict) else gid)
            await self.store.upsert_edge(
                tenant_id,
                "BELONGS_TO",
                pid,
                gid,
                source_label="Person",
                target_label="Group",
            )

        logger.info("Graph upserted person=%s tenant=%s", pid, tenant_id)
        return pid

    async def _handle_group(
        self, tenant_id: str, payload: Dict[str, Any], event_type: str
    ) -> Optional[str]:
        gid = payload.get("group_id") or payload.get("source_id") or payload.get("id")
        if not gid:
            logger.error("group event missing id: %s", payload)
            return None
        gid = str(gid)
        props = {
            "display_name": payload.get("display_name") or payload.get("name"),
            "email": payload.get("email"),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }
        await self.store.upsert_node(tenant_id, "Group", gid, props)

        for member in payload.get("member_ids") or payload.get("members") or []:
            mid = str(member.get("id") if isinstance(member, dict) else member)
            await self.store.upsert_edge(
                tenant_id,
                "BELONGS_TO",
                mid,
                gid,
                source_label="Person",
                target_label="Group",
            )

        for parent in payload.get("member_of") or payload.get("parent_groups") or []:
            parent_id = str(parent.get("id") if isinstance(parent, dict) else parent)
            await self.store.upsert_edge(
                tenant_id,
                "MEMBER_OF",
                gid,
                parent_id,
                source_label="Group",
                target_label="Group",
            )

        logger.info("Graph upserted group=%s tenant=%s", gid, tenant_id)
        return gid

    async def _handle_acl(
        self, tenant_id: str, payload: Dict[str, Any], event_type: str
    ) -> Optional[str]:
        """ACL changes may add SHARED_WITH edges; document node stays."""
        doc_id = payload.get("document_id") or payload.get("source_id")
        if doc_id:
            await self.store.upsert_node(
                tenant_id,
                "Document",
                str(doc_id),
                {
                    "visibility_mode": payload.get("visibility_mode"),
                    "updated_at": payload.get("updated_at"),
                },
            )
        return str(doc_id) if doc_id else None

    async def _handle_activity_viewed(
        self, tenant_id: str, payload: Dict[str, Any], event_type: str
    ) -> Optional[str]:
        person = payload.get("principal_id") or payload.get("person_id")
        doc = payload.get("document_id")
        if not person or not doc:
            return None
        await self.store.upsert_edge(
            tenant_id,
            "VIEWED",
            str(person),
            str(doc),
            source_label="Person",
            target_label="Document",
        )
        return str(doc)

    async def _handle_activity_commented(
        self, tenant_id: str, payload: Dict[str, Any], event_type: str
    ) -> Optional[str]:
        person = payload.get("principal_id") or payload.get("person_id")
        doc = payload.get("document_id")
        if not person or not doc:
            return None
        await self.store.upsert_edge(
            tenant_id,
            "COMMENTED_ON",
            str(person),
            str(doc),
            source_label="Person",
            target_label="Document",
        )
        return str(doc)


# Alias matching master-prompt naming
CanonicalGraphConsumer = GraphWriter
