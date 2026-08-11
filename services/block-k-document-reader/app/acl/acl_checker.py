"""ACL re-check via Block C — no caching (K1)."""

from __future__ import annotations

import logging
from typing import Protocol, Set, Tuple

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class ACLChecker(Protocol):
    async def is_allowed(
        self, tenant_id: str, principal_id: str, doc_id: str
    ) -> bool: ...


class MockACLChecker:
    """Phase 1 / in-process ACL. No caching — each call reads current state."""

    def __init__(self) -> None:
        self._allowed: Set[Tuple[str, str, str]] = set()
        self.call_count: int = 0
        self._history: list[Tuple[str, str, str, bool]] = []

    def grant(self, tenant_id: str, doc_id: str, principal_id: str) -> None:
        self._allowed.add((tenant_id, doc_id, principal_id))

    def revoke(self, tenant_id: str, doc_id: str, principal_id: str) -> None:
        self._allowed.discard((tenant_id, doc_id, principal_id))

    def clear(self) -> None:
        self._allowed.clear()
        self.call_count = 0
        self._history.clear()

    async def is_allowed(
        self, tenant_id: str, principal_id: str, doc_id: str
    ) -> bool:
        self.call_count += 1
        allowed = (tenant_id, doc_id, principal_id) in self._allowed
        self._history.append((tenant_id, principal_id, doc_id, allowed))
        return allowed


class HttpACLChecker:
    """Phase 2 — call Block C /acl/compile with no local cache."""

    def __init__(self, acl_service_url: str, timeout: float = 5.0) -> None:
        self.acl_service_url = acl_service_url.rstrip("/")
        self.timeout = timeout

    async def is_allowed(
        self, tenant_id: str, principal_id: str, doc_id: str
    ) -> bool:
        url = f"{self.acl_service_url}/acl/compile"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    url,
                    json={
                        "tenant_id": tenant_id,
                        "principal_id": principal_id,
                        "document_id": doc_id,
                    },
                )
        except httpx.HTTPError as exc:
            logger.error("ACL service unreachable: %s", exc)
            raise HTTPException(status_code=500, detail="ACL service unavailable") from exc

        if resp.status_code != 200:
            logger.error("ACL service status=%s body=%s", resp.status_code, resp.text)
            raise HTTPException(status_code=500, detail="ACL service unavailable")

        data = resp.json()
        if "allowed" in data:
            return bool(data["allowed"])
        if "decision" in data:
            return str(data["decision"]).lower() in {"allow", "allowed", "permit"}
        if "access" in data:
            return str(data["access"]).lower() in {"allow", "allowed", "permit"}
        return False


async def check_acl(
    checker: ACLChecker,
    tenant_id: str,
    principal_id: str,
    doc_id: str,
) -> bool:
    """Re-evaluate access on every call — never cache (K1)."""
    return await checker.is_allowed(tenant_id, principal_id, doc_id)


def create_acl_checker(settings) -> MockACLChecker | HttpACLChecker:
    if settings.acl_backend == "http":
        return HttpACLChecker(settings.acl_service_url)
    return MockACLChecker()
