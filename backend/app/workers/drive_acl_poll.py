"""Drive ACL poll fallback: enqueue the existing webhook incremental task."""

from __future__ import annotations

from typing import Callable, Iterable, List


def enqueue_drive_acl_poll(
    tenant_ids: Iterable[str],
    delay: Callable[[str], object],
) -> dict:
    ids: List[str] = [str(tid) for tid in tenant_ids if tid]
    for tenant_id in ids:
        delay(tenant_id)
    return {"enqueued": len(ids), "tenants": ids}
