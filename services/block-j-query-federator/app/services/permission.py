"""ACL post-check against acl_entries (batch IN query)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import UserContext

logger = logging.getLogger(__name__)


@dataclass
class ACLEntryRecord:
    """Single materialized ACL grant/deny."""

    doc_id: str
    principal_id: Optional[str] = None
    group_id: Optional[str] = None
    permission_type: str = "read"
    is_deny: bool = False
    tenant_id: str = ""


@dataclass
class InMemoryACLStore:
    """Process-local ACL store used in tests and ACL_BACKEND=memory."""

    entries: List[ACLEntryRecord] = field(default_factory=list)

    def replace_all(self, entries: Iterable[ACLEntryRecord]) -> None:
        self.entries = list(entries)

    def add(self, entry: ACLEntryRecord) -> None:
        self.entries.append(entry)

    def clear(self) -> None:
        self.entries.clear()


# Module-level memory store (populated by fixtures / startup)
memory_acl_store = InMemoryACLStore()


class ACLStore:
    """Facade over memory or postgres ACL backends."""

    def __init__(self, memory: Optional[InMemoryACLStore] = None) -> None:
        self.memory = memory or memory_acl_store

    async def allowed_document_ids(
        self,
        doc_ids: List[str],
        user_context: UserContext,
        db_session: Optional[AsyncSession] = None,
    ) -> Set[str]:
        return await check_documents_access(doc_ids, user_context, db_session, store=self.memory)


async def check_documents_access(
    doc_ids: List[str],
    user_context: UserContext,
    db_session: Optional[AsyncSession] = None,
    store: Optional[InMemoryACLStore] = None,
) -> Set[str]:
    """
    Return the subset of ``doc_ids`` the principal may read.

    Rules (fail-closed):
    - Empty input → empty set
    - Deny matching principal/group wins over allow
    - Allow if principal_id matches OR group_id is in the caller's groups/acl_terms
    - permission_type must be a read-capable grant (read|write|admin)
    """
    if not doc_ids:
        return set()

    unique_ids = list(dict.fromkeys(doc_ids))
    acl_terms = set(user_context.build_acl_terms())
    principal = user_context.principal_id
    tenant_id = user_context.tenant_id

    if settings.acl_backend == "postgres" and db_session is not None:
        return await _check_postgres(
            unique_ids, principal, acl_terms, tenant_id, db_session
        )

    mem = store or memory_acl_store
    return _check_memory(unique_ids, principal, acl_terms, tenant_id, mem)


async def _check_postgres(
    doc_ids: List[str],
    principal: str,
    acl_terms: Set[str],
    tenant_id: str,
    session: AsyncSession,
) -> Set[str]:
    """Batch query acl_entries with IN clause (chunked)."""
    allowed: Set[str] = set()
    denied: Set[str] = set()
    batch_size = max(1, settings.acl_batch_size)

    for i in range(0, len(doc_ids), batch_size):
        batch = doc_ids[i : i + batch_size]
        result = await session.execute(
            text(
                """
                SELECT doc_id, principal_id, group_id, permission_type, is_deny
                FROM acl_entries
                WHERE tenant_id = :tenant_id
                  AND doc_id = ANY(:doc_ids)
                  AND permission_type IN ('read', 'write', 'admin', 'owner')
                """
            ),
            {"tenant_id": tenant_id, "doc_ids": batch},
        )
        rows = result.fetchall()
        for row in rows:
            doc_id, principal_id, group_id, _perm, is_deny = row
            matches = False
            if principal_id and (principal_id == principal or principal_id in acl_terms):
                matches = True
            if group_id and group_id in acl_terms:
                matches = True
            if not matches:
                continue
            if is_deny:
                denied.add(doc_id)
            else:
                allowed.add(doc_id)

    return allowed - denied


def _check_memory(
    doc_ids: List[str],
    principal: str,
    acl_terms: Set[str],
    tenant_id: str,
    store: InMemoryACLStore,
) -> Set[str]:
    by_doc: Dict[str, List[ACLEntryRecord]] = {}
    for entry in store.entries:
        if entry.tenant_id and entry.tenant_id != tenant_id:
            continue
        by_doc.setdefault(entry.doc_id, []).append(entry)

    allowed: Set[str] = set()
    for doc_id in doc_ids:
        entries = by_doc.get(doc_id, [])
        if not entries:
            # Fail-closed: no ACL row ⇒ not visible
            continue
        denied = False
        granted = False
        for entry in entries:
            if entry.permission_type not in ("read", "write", "admin", "owner"):
                continue
            matches = False
            if entry.principal_id and (
                entry.principal_id == principal or entry.principal_id in acl_terms
            ):
                matches = True
            if entry.group_id and entry.group_id in acl_terms:
                matches = True
            if not matches:
                continue
            if entry.is_deny:
                denied = True
            else:
                granted = True
        if granted and not denied:
            allowed.add(doc_id)
    return allowed
