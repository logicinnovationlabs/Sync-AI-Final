"""
Canonical repository for Block C persistence.

Handles CanonicalDocument, Principal, Group, ACLEntry, ContainerACLEntry,
and ContainerEdge persistence in the per-tenant Postgres database.

All SQL operations are tenant-scoped via the session supplied by Block A's
TenantResolver-provisioned connection. In-memory mode remains the default so
Block C signoff tests stay isolated.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    CanonicalDocument,
    Principal,
    Group,
    ACLEntry,
    ContainerACLEntry,
    ContainerEdge,
    PermissionLevel,
)
from app.models.canonical import (
    CanonicalDocumentRow,
    IdentityPrincipalRow,
    IdentityGroupRow,
    ACLEntryRow,
    ContainerACLEntryRow,
    ContainerEdgeRow,
)

logger = logging.getLogger(__name__)


def _as_uuid(value) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _uuid_list(values) -> List[str]:
    return [str(v) for v in (values or [])]


def _parse_uuid_list(values) -> list:
    out = []
    for item in values or []:
        try:
            out.append(UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return out


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _doc_from_row(row: CanonicalDocumentRow) -> CanonicalDocument:
    return CanonicalDocument(
        id=row.id,
        source_type=row.source_type,
        source_id=row.source_id,
        tenant_id=row.tenant_id,
        title=row.title,
        content=row.content or "",
        url=row.url,
        mime_type=row.mime_type or "",
        detected_mime_type=row.detected_mime_type or "",
        mime_mismatch=bool(row.mime_mismatch),
        file_extension=row.file_extension,
        size_bytes=row.size_bytes,
        created_at=row.source_created_at,
        updated_at=row.updated_at,
        source_updated_at=row.source_updated_at,
        owner_principal_id=row.owner_principal_id,
        creator_principal_id=row.creator_principal_id,
        last_modifier_principal_id=row.last_modifier_principal_id,
        structured_metadata=dict(row.structured_metadata or {}),
        parent_ids=list(row.parent_ids or []),
    )


def _principal_from_row(row: IdentityPrincipalRow) -> Principal:
    return Principal(
        id=row.id,
        tenant_id=row.tenant_id,
        email=row.email,
        name=row.name,
        source_identities=dict(row.source_identities or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _group_from_row(row: IdentityGroupRow) -> Group:
    return Group(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        email=row.email,
        source_type=row.source_type,
        source_id=row.source_id,
        member_principal_ids=_parse_uuid_list(row.member_principal_ids),
        member_group_ids=_parse_uuid_list(row.member_group_ids),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _acl_from_row(row: ACLEntryRow) -> ACLEntry:
    return ACLEntry(
        document_id=row.document_id,
        principal_id=row.principal_id,
        group_id=row.group_id,
        permission=PermissionLevel(row.permission),
        granted_via=row.granted_via,
        source_container_id=row.source_container_id,
        is_deny=bool(row.is_deny),
        source_type=row.source_type,
        tenant_id=row.tenant_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _container_acl_from_row(row: ContainerACLEntryRow) -> ContainerACLEntry:
    return ContainerACLEntry(
        container_id=row.container_id,
        principal_id=row.principal_id,
        group_id=row.group_id,
        permission=PermissionLevel(row.permission),
        is_deny=bool(row.is_deny),
        source_type=row.source_type,
        tenant_id=row.tenant_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class CanonicalRepo:
    """
    Repository for canonical document and ACL persistence.

    use_memory=True (default) keeps Block C tests on an isolated in-memory map.
    Production HTTP routes pass a tenant-scoped AsyncSession.
    """

    def __init__(self, use_memory: bool = True, session: Optional[AsyncSession] = None):
        self.use_memory = use_memory if session is None else False
        if session is not None:
            self.use_memory = False
        self.session = session

        self._documents: dict[str, CanonicalDocument] = {}
        self._principals: dict[UUID, Principal] = {}
        self._principals_by_email: dict[tuple[UUID, str], Principal] = {}
        self._groups: dict[UUID, Group] = {}
        self._groups_by_email: dict[tuple[UUID, str], Group] = {}
        self._groups_by_source: dict[tuple[str, str, UUID], Group] = {}
        self._acl_entries: dict[str, List[ACLEntry]] = {}
        self._container_acl_entries: dict[tuple[str, UUID], List[ContainerACLEntry]] = {}
        self._container_edges: dict[tuple[str, UUID], Optional[str]] = {}

    def _sql(self) -> AsyncSession:
        if self.use_memory:
            raise RuntimeError("CanonicalRepo SQL path requested while use_memory=True")
        if self.session is None:
            raise RuntimeError("CanonicalRepo SQL path requires a tenant database session")
        return self.session

    # ============================================================
    # CANONICAL DOCUMENT METHODS
    # ============================================================

    async def upsert_document(self, doc: CanonicalDocument) -> None:
        if self.use_memory:
            self._documents[doc.id] = doc
            return
        session = self._sql()
        values = {
            "id": doc.id,
            "source_type": doc.source_type,
            "source_id": doc.source_id,
            "tenant_id": _as_uuid(doc.tenant_id),
            "title": doc.title,
            "content": doc.content or "",
            "url": doc.url,
            "mime_type": doc.mime_type or "",
            "detected_mime_type": doc.detected_mime_type or "",
            "mime_mismatch": bool(doc.mime_mismatch),
            "file_extension": doc.file_extension,
            "size_bytes": doc.size_bytes,
            "source_created_at": _aware(doc.created_at),
            "source_updated_at": _aware(doc.source_updated_at),
            "owner_principal_id": doc.owner_principal_id,
            "creator_principal_id": doc.creator_principal_id,
            "last_modifier_principal_id": doc.last_modifier_principal_id,
            "structured_metadata": dict(doc.structured_metadata or {}),
            "parent_ids": list(doc.parent_ids or []),
        }
        stmt = pg_insert(CanonicalDocumentRow).values(**values)
        update_cols = {k: stmt.excluded[k] for k in values if k != "id"}
        await session.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols))
        await session.commit()

    async def get_document(self, document_id: str) -> Optional[CanonicalDocument]:
        if self.use_memory:
            return self._documents.get(document_id)
        session = self._sql()
        row = await session.get(CanonicalDocumentRow, document_id)
        return _doc_from_row(row) if row else None

    async def delete_documents_and_acls(self, document_ids: List[str], tenant_id: UUID) -> None:
        if self.use_memory:
            for doc_id in document_ids:
                self._documents.pop(doc_id, None)
                self._acl_entries.pop(doc_id, None)
            return
        session = self._sql()
        tenant = _as_uuid(tenant_id)
        if document_ids:
            await session.execute(
                delete(ACLEntryRow).where(
                    ACLEntryRow.document_id.in_(document_ids),
                    ACLEntryRow.tenant_id == tenant,
                )
            )
            await session.execute(
                delete(CanonicalDocumentRow).where(
                    CanonicalDocumentRow.id.in_(document_ids),
                    CanonicalDocumentRow.tenant_id == tenant,
                )
            )
            await session.commit()

    # ============================================================
    # PRINCIPAL METHODS
    # ============================================================

    async def create_principal(self, principal: Principal) -> None:
        if self.use_memory:
            email_key = (principal.tenant_id, principal.email.lower())
            if email_key in self._principals_by_email:
                raise ValueError(
                    f"Principal with email {principal.email} already exists in tenant {principal.tenant_id}"
                )
            self._principals[principal.id] = principal
            self._principals_by_email[email_key] = principal
            return
        session = self._sql()
        session.add(
            IdentityPrincipalRow(
                id=_as_uuid(principal.id),
                tenant_id=_as_uuid(principal.tenant_id),
                email=principal.email.lower(),
                name=principal.name,
                source_identities=dict(principal.source_identities or {}),
            )
        )
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError(
                f"Principal with email {principal.email} already exists in tenant {principal.tenant_id}"
            ) from exc

    async def update_principal(self, principal: Principal) -> None:
        if self.use_memory:
            self._principals[principal.id] = principal
            email_key = (principal.tenant_id, principal.email.lower())
            self._principals_by_email[email_key] = principal
            return
        session = self._sql()
        row = await session.get(IdentityPrincipalRow, _as_uuid(principal.id))
        if row is None:
            await self.create_principal(principal)
            return
        row.email = principal.email.lower()
        row.name = principal.name
        row.source_identities = dict(principal.source_identities or {})
        await session.commit()

    async def get_principal_by_email(self, email: str, tenant_id: UUID) -> Optional[Principal]:
        if self.use_memory:
            return self._principals_by_email.get((_as_uuid(tenant_id), email.lower()))
        session = self._sql()
        result = await session.execute(
            select(IdentityPrincipalRow).where(
                IdentityPrincipalRow.tenant_id == _as_uuid(tenant_id),
                IdentityPrincipalRow.email == email.lower(),
            )
        )
        row = result.scalar_one_or_none()
        return _principal_from_row(row) if row else None

    async def get_principal_by_source_identity(
        self, source_type: str, external_id: str, tenant_id: UUID
    ) -> Optional[Principal]:
        if self.use_memory:
            for principal in self._principals.values():
                if principal.tenant_id == tenant_id:
                    if principal.source_identities.get(source_type) == external_id:
                        return principal
            return None
        session = self._sql()
        result = await session.execute(
            select(IdentityPrincipalRow).where(
                IdentityPrincipalRow.tenant_id == _as_uuid(tenant_id),
                IdentityPrincipalRow.source_identities.contains({source_type: external_id}),
            )
        )
        row = result.scalar_one_or_none()
        return _principal_from_row(row) if row else None

    # ============================================================
    # GROUP METHODS
    # ============================================================

    async def create_group(self, group: Group) -> None:
        if self.use_memory:
            self._groups[group.id] = group
            if group.email:
                self._groups_by_email[(group.tenant_id, group.email.lower())] = group
            self._groups_by_source[(group.source_type, group.source_id, group.tenant_id)] = group
            return
        session = self._sql()
        session.add(
            IdentityGroupRow(
                id=_as_uuid(group.id),
                tenant_id=_as_uuid(group.tenant_id),
                name=group.name,
                email=group.email.lower() if group.email else None,
                source_type=group.source_type,
                source_id=group.source_id,
                member_principal_ids=_uuid_list(group.member_principal_ids),
                member_group_ids=_uuid_list(group.member_group_ids),
            )
        )
        await session.commit()

    async def get_group(self, group_id: UUID, tenant_id: UUID) -> Optional[Group]:
        if self.use_memory:
            group = self._groups.get(group_id)
            if group and group.tenant_id == tenant_id:
                return group
            return None
        session = self._sql()
        row = await session.get(IdentityGroupRow, _as_uuid(group_id))
        if row is None or row.tenant_id != _as_uuid(tenant_id):
            return None
        return _group_from_row(row)

    async def get_group_by_email(self, email: str, tenant_id: UUID) -> Optional[Group]:
        if self.use_memory:
            return self._groups_by_email.get((_as_uuid(tenant_id), email.lower()))
        session = self._sql()
        result = await session.execute(
            select(IdentityGroupRow).where(
                IdentityGroupRow.tenant_id == _as_uuid(tenant_id),
                IdentityGroupRow.email == email.lower(),
            )
        )
        row = result.scalar_one_or_none()
        return _group_from_row(row) if row else None

    async def get_group_by_source_identity(
        self, source_type: str, source_id: str, tenant_id: UUID
    ) -> Optional[Group]:
        if self.use_memory:
            return self._groups_by_source.get((source_type, source_id, tenant_id))
        session = self._sql()
        result = await session.execute(
            select(IdentityGroupRow).where(
                IdentityGroupRow.source_type == source_type,
                IdentityGroupRow.source_id == source_id,
                IdentityGroupRow.tenant_id == _as_uuid(tenant_id),
            )
        )
        row = result.scalar_one_or_none()
        return _group_from_row(row) if row else None

    # ============================================================
    # ACL ENTRY METHODS
    # ============================================================

    async def replace_acl_entries(self, document_id: str, entries: List[ACLEntry]) -> None:
        if self.use_memory:
            self._acl_entries[document_id] = entries
            return
        session = self._sql()
        await session.execute(delete(ACLEntryRow).where(ACLEntryRow.document_id == document_id))
        for entry in entries:
            session.add(
                ACLEntryRow(
                    document_id=document_id,
                    principal_id=entry.principal_id,
                    group_id=entry.group_id,
                    permission=entry.permission.value if isinstance(entry.permission, PermissionLevel) else str(entry.permission),
                    granted_via=entry.granted_via,
                    source_container_id=entry.source_container_id,
                    is_deny=bool(entry.is_deny),
                    source_type=entry.source_type,
                    tenant_id=_as_uuid(entry.tenant_id),
                )
            )
        await session.commit()

    async def get_acl_entries(self, document_id: str) -> List[ACLEntry]:
        if self.use_memory:
            return self._acl_entries.get(document_id, [])
        session = self._sql()
        result = await session.execute(
            select(ACLEntryRow).where(ACLEntryRow.document_id == document_id)
        )
        return [_acl_from_row(row) for row in result.scalars().all()]

    # ============================================================
    # CONTAINER ACL ENTRY METHODS
    # ============================================================

    async def upsert_container_acl(self, entry: ContainerACLEntry) -> None:
        if self.use_memory:
            key = (entry.container_id, entry.tenant_id)
            if key not in self._container_acl_entries:
                self._container_acl_entries[key] = []
            existing = self._container_acl_entries[key]
            existing[:] = [
                e
                for e in existing
                if not (e.principal_id == entry.principal_id and e.group_id == entry.group_id)
            ]
            existing.append(entry)
            return
        session = self._sql()
        tenant = _as_uuid(entry.tenant_id)
        result = await session.execute(
            select(ContainerACLEntryRow).where(
                ContainerACLEntryRow.container_id == entry.container_id,
                ContainerACLEntryRow.tenant_id == tenant,
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            if row.principal_id == entry.principal_id and row.group_id == entry.group_id:
                await session.delete(row)
        session.add(
            ContainerACLEntryRow(
                container_id=entry.container_id,
                principal_id=entry.principal_id,
                group_id=entry.group_id,
                permission=entry.permission.value if isinstance(entry.permission, PermissionLevel) else str(entry.permission),
                is_deny=bool(entry.is_deny),
                source_type=entry.source_type,
                tenant_id=tenant,
            )
        )
        await session.commit()

    async def get_container_acl_entries(
        self, container_id: str, tenant_id: UUID
    ) -> List[ContainerACLEntry]:
        if self.use_memory:
            return self._container_acl_entries.get((container_id, tenant_id), [])
        session = self._sql()
        result = await session.execute(
            select(ContainerACLEntryRow).where(
                ContainerACLEntryRow.container_id == container_id,
                ContainerACLEntryRow.tenant_id == _as_uuid(tenant_id),
            )
        )
        return [_container_acl_from_row(row) for row in result.scalars().all()]

    # ============================================================
    # CONTAINER EDGE METHODS
    # ============================================================

    async def upsert_container_edge(self, edge: ContainerEdge) -> None:
        if self.use_memory:
            self._container_edges[(edge.child_container_id, edge.tenant_id)] = edge.parent_container_id
            return
        session = self._sql()
        tenant = _as_uuid(edge.tenant_id)
        values = {
            "parent_container_id": edge.parent_container_id,
            "child_container_id": edge.child_container_id,
            "tenant_id": tenant,
            "source_type": edge.source_type,
        }
        stmt = pg_insert(ContainerEdgeRow).values(**values)
        await session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_container_edges_child_tenant",
                set_={
                    "parent_container_id": stmt.excluded.parent_container_id,
                    "source_type": stmt.excluded.source_type,
                },
            )
        )
        await session.commit()

    async def get_parent_container(self, child_id: str, tenant_id: UUID) -> Optional[str]:
        if self.use_memory:
            return self._container_edges.get((child_id, tenant_id))
        session = self._sql()
        result = await session.execute(
            select(ContainerEdgeRow).where(
                ContainerEdgeRow.child_container_id == child_id,
                ContainerEdgeRow.tenant_id == _as_uuid(tenant_id),
            )
        )
        row = result.scalar_one_or_none()
        return row.parent_container_id if row else None

    async def delete_container(self, container_id: str, tenant_id: UUID) -> None:
        if self.use_memory:
            key = (container_id, tenant_id)
            self._container_acl_entries.pop(key, None)
            keys_to_delete = [
                k
                for k, v in self._container_edges.items()
                if k[0] == container_id or v == container_id
            ]
            for k in keys_to_delete:
                self._container_edges.pop(k, None)
            return
        session = self._sql()
        tenant = _as_uuid(tenant_id)
        await session.execute(
            delete(ContainerACLEntryRow).where(
                ContainerACLEntryRow.container_id == container_id,
                ContainerACLEntryRow.tenant_id == tenant,
            )
        )
        await session.execute(
            delete(ContainerEdgeRow).where(
                ContainerEdgeRow.tenant_id == tenant,
                (ContainerEdgeRow.child_container_id == container_id)
                | (ContainerEdgeRow.parent_container_id == container_id),
            )
        )
        await session.commit()
