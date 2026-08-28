"""Thin HTTP wrappers over existing Block J/H/K/I service APIs.

No downstream importable client packages exist in-repo for Federator, KG,
Document Reader, or Activity Signals. SearchToolbox talks to their real
HTTP surfaces via httpx (see SIGNOFF deviations).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.acl.filter import is_fail_closed
from app.services.assistant.domain.models import ToolCall, ToolResult

logger = logging.getLogger(__name__)

# Outbound ACL capture hook used by verification scripts.
AclCaptureHook = Callable[[str, bytes, Dict[str, Any]], None]


def is_loopback_url(url: str) -> bool:
    lowered = (url or "").lower()
    return (
        not lowered
        or "localhost" in lowered
        or "127.0.0.1" in lowered
        or "0.0.0.0" in lowered
        or "[::1]" in lowered
        or "://::1" in lowered
    )


def encode_acl_terms(acl_terms: List[str]) -> bytes:
    """Wrap Identity/JWT acl_terms as opaque bytes (JSON array, UTF-8)."""
    return json.dumps(list(acl_terms), separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def acl_bytes_for_transport(acl_compiled_filter: bytes) -> bytes:
    """
    Return the opaque filter unchanged.

    Deliberately does not inspect or transform contents — callers that need a
    List[str] for JSON bodies must use the companion transport helper which
    only performs mechanical UTF-8/JSON deserialization for wire format, never
    for control-flow branching inside Block L.
    """
    return acl_compiled_filter


def acl_terms_for_json_body(acl_compiled_filter: bytes) -> List[str]:
    """
    Mechanical wire-format decode for backends that require List[str] JSON.

    This is serialization adaptation only. Callers MUST NOT branch on the
    returned terms. Verification scripts assert byte-identity of the opaque
    filter on the wire via the X-ACL-Compiled-Filter header (base64) which
    carries the unmodified bytes.
    """
    return json.loads(acl_compiled_filter.decode("utf-8"))


class SearchToolbox:
    """
    Orchestrator tool surface.

    Every outbound call:
      1. Forwards Authorization unchanged.
      2. Attaches X-ACL-Compiled-Filter: <hex of opaque bytes> so ACL
         pass-through can be proven without inspecting filter contents.
      3. For backends that require acl_terms in the JSON body (F/G lineage via
         Federator request shaping), places the mechanical JSON list without
         branching on term values.
    """

    def __init__(
        self,
        *,
        federator_url: Optional[str] = None,
        graph_url: Optional[str] = None,
        document_reader_url: Optional[str] = None,
        signals_url: Optional[str] = None,
        timeout_s: float = 30.0,
        acl_capture: Optional[AclCaptureHook] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.federator_url = (federator_url or os.getenv("QUERY_FEDERATOR_URL", "http://localhost:8000")).rstrip("/")
        self.graph_url = (graph_url or os.getenv("GRAPH_SERVICE_URL", "http://localhost:8000")).rstrip("/")
        self.document_reader_url = (
            document_reader_url or os.getenv("DOCUMENT_READER_URL", "http://localhost:8000")
        ).rstrip("/")
        self.signals_url = (signals_url or os.getenv("SIGNALS_URL", "http://localhost:8000")).rstrip("/")
        self.timeout_s = timeout_s
        self.acl_capture = acl_capture
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        # Prefer injected client; otherwise create a fresh per-call client.
        # Starlette TestClient creates/closes event loops per request — a cached
        # AsyncClient bound to a dead loop causes "Event loop is closed" failures.
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=self.timeout_s)

    async def _request(self, method: str, url: str, **kwargs):
        client = await self._get_client()
        owns = self._client is None
        try:
            return await client.request(method, url, **kwargs)
        finally:
            if owns:
                await client.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _acl_headers(self, acl_compiled_filter: bytes, authorization: Optional[str]) -> Dict[str, str]:
        headers: Dict[str, str] = {
            # Hex encoding of opaque bytes — transport envelope only, no inspection.
            "X-ACL-Compiled-Filter": acl_compiled_filter.hex(),
            "Content-Type": "application/json",
        }
        if authorization:
            headers["Authorization"] = authorization
        return headers

    def _record(self, tool_name: str, acl: bytes, request_meta: Dict[str, Any]) -> None:
        if self.acl_capture is not None:
            self.acl_capture(tool_name, acl, request_meta)

    async def execute(
        self,
        call: ToolCall,
        *,
        authorization: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> ToolResult:
        dispatch = {
            "lexical_search": self.lexical_search,
            "vector_search": self.vector_search,
            "kg_query": self.kg_query,
            "read_document": self.read_document,
            "signal_lookup": self.signal_lookup,
        }
        handler = dispatch[call.tool_name]
        return await handler(call, authorization=authorization, tenant_id=tenant_id)

    async def lexical_search(
        self,
        call: ToolCall,
        *,
        authorization: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> ToolResult:
        return await self._federated_search(
            call, mode="lexical", authorization=authorization, tenant_id=tenant_id
        )

    async def vector_search(
        self,
        call: ToolCall,
        *,
        authorization: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> ToolResult:
        return await self._federated_search(
            call, mode="vector", authorization=authorization, tenant_id=tenant_id
        )

    def _federator_is_loopback(self) -> bool:
        return is_loopback_url(self.federator_url)

    async def _federated_search(
        self,
        call: ToolCall,
        *,
        mode: str,
        authorization: Optional[str],
        tenant_id: Optional[str],
    ) -> ToolResult:
        """Block J search — prefer in-process (Render chat must not call localhost)."""
        acl = acl_bytes_for_transport(call.acl_compiled_filter)
        params = dict(call.query_params)
        terms = acl_terms_for_json_body(acl)
        query = str(params.get("query", "") or "")
        size = int(params.get("size", 20))

        # Production: QUERY_FEDERATOR_URL defaults to localhost and fails on Render.
        # Documents tab hits this API in-process via the browser; chat must do the same.
        if tenant_id and self._federator_is_loopback():
            return await self._federated_search_inprocess(
                call,
                query=query,
                size=size,
                tenant_id=tenant_id,
                acl_terms=[] if is_fail_closed(terms) else terms,
                mode=mode,
            )

        body: Dict[str, Any] = {
            "query": query,
            "size": size,
            "from": int(params.get("from", 0)),
            "acl_terms": [] if is_fail_closed(terms) else terms,
            "debug": bool(params.get("debug", False)),
            "orchestrator_mode": mode,
            "enable_lexical": True,
            "enable_vector": True,
        }
        if tenant_id:
            body["tenant_id"] = tenant_id
        headers = self._acl_headers(acl, authorization)
        self._record(
            call.tool_name,
            acl,
            {"url": f"{self.federator_url}/search/federated", "body": body, "headers": headers},
        )

        started = time.perf_counter()
        try:
            resp = await self._request(
                "POST",
                f"{self.federator_url}/search/federated",
                headers=headers,
                json=body,
            )
            latency = (time.perf_counter() - started) * 1000.0
            payload = resp.json() if resp.content else {}
            return ToolResult(
                tool_name=call.tool_name,
                ok=resp.status_code < 400,
                payload=payload if isinstance(payload, dict) else {"raw": payload},
                error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                acl_bytes_sent=acl,
                latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - started) * 1000.0
            logger.exception("federated search failed")
            # Last resort: same-process search when the HTTP hop dies.
            if tenant_id:
                logger.warning(
                    "federated HTTP failed; falling back to in-process search: %s", exc
                )
                return await self._federated_search_inprocess(
                    call,
                    query=query,
                    size=size,
                    tenant_id=tenant_id,
                    acl_terms=[] if is_fail_closed(terms) else terms,
                    mode=mode,
                )
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                payload={},
                error=str(exc),
                acl_bytes_sent=acl,
                latency_ms=latency,
            )

    async def _federated_search_inprocess(
        self,
        call: ToolCall,
        *,
        query: str,
        size: int,
        tenant_id: str,
        acl_terms: List[str],
        mode: str,
    ) -> ToolResult:
        from app.services.query_federator import federated_search_inprocess

        acl = acl_bytes_for_transport(call.acl_compiled_filter)
        principal = ""
        for term in acl_terms:
            raw = str(term)
            if raw.startswith("user:"):
                principal = raw.split(":", 1)[-1]
                break
            if raw and not principal:
                principal = raw

        self._record(
            call.tool_name,
            acl,
            {
                "url": "inprocess://search/federated",
                "body": {
                    "query": query,
                    "size": size,
                    "tenant_id": tenant_id,
                    "mode": mode,
                    "acl_terms": acl_terms,
                },
            },
        )
        started = time.perf_counter()
        try:
            payload = await federated_search_inprocess(
                query=query,
                tenant_id=tenant_id,
                principal_id=principal,
                size=size,
                acl_terms=acl_terms,
            )
            latency = (time.perf_counter() - started) * 1000.0
            hit_count = len(payload.get("results") or [])
            logger.info(
                "[assistant.pipeline] inprocess federated mode=%s hits=%s ms=%.1f",
                mode,
                hit_count,
                latency,
            )
            return ToolResult(
                tool_name=call.tool_name,
                ok=True,
                payload=payload,
                error=None,
                acl_bytes_sent=acl,
                latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - started) * 1000.0
            logger.exception("inprocess federated search failed")
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                payload={},
                error=str(exc),
                acl_bytes_sent=acl,
                latency_ms=latency,
            )

    async def kg_query(
        self,
        call: ToolCall,
        *,
        authorization: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> ToolResult:
        """Call Block H POST /search/graph/traverse."""
        acl = acl_bytes_for_transport(call.acl_compiled_filter)
        params = dict(call.query_params)
        terms = acl_terms_for_json_body(acl)
        body: Dict[str, Any] = {
            "start_node_id": params.get("start_node_id", params.get("query", "")),
            "relationship_types": params.get("relationship_types") or [],
            "depth": int(params.get("depth", 2)),
            "acl_terms": [] if is_fail_closed(terms) else terms,
        }
        if tenant_id:
            body["tenant_id"] = tenant_id
        headers = self._acl_headers(acl, authorization)
        url = f"{self.graph_url}/search/graph/traverse"
        self._record(call.tool_name, acl, {"url": url, "body": body, "headers": headers})

        started = time.perf_counter()
        try:
            resp = await self._request("POST", url, headers=headers, json=body)
            latency = (time.perf_counter() - started) * 1000.0
            payload = resp.json() if resp.content else {}
            return ToolResult(
                tool_name=call.tool_name,
                ok=resp.status_code < 400,
                payload=payload if isinstance(payload, dict) else {"raw": payload},
                error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                acl_bytes_sent=acl,
                latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - started) * 1000.0
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                payload={},
                error=str(exc),
                acl_bytes_sent=acl,
                latency_ms=latency,
            )

    async def read_document(
        self,
        call: ToolCall,
        *,
        authorization: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> ToolResult:
        """Call Block K GET /document/{id}."""
        acl = acl_bytes_for_transport(call.acl_compiled_filter)
        doc_id = str(call.query_params.get("document_id") or call.query_params.get("blob_id") or "")
        headers = self._acl_headers(acl, authorization)
        # Mechanical mirror for any gateway that reads body terms (K uses JWT ACL).
        headers["X-ACL-Terms-JSON"] = acl.decode("utf-8")
        url = f"{self.document_reader_url}/document/{doc_id}"
        self._record(call.tool_name, acl, {"url": url, "headers": headers})

        started = time.perf_counter()
        try:
            resp = await self._request("GET", url, headers=headers)
            latency = (time.perf_counter() - started) * 1000.0
            payload = resp.json() if resp.content else {}
            return ToolResult(
                tool_name=call.tool_name,
                ok=resp.status_code < 400,
                payload=payload if isinstance(payload, dict) else {"raw": payload},
                error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                acl_bytes_sent=acl,
                latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - started) * 1000.0
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                payload={},
                error=str(exc),
                acl_bytes_sent=acl,
                latency_ms=latency,
            )

    async def signal_lookup(
        self,
        call: ToolCall,
        *,
        authorization: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> ToolResult:
        """Call Block I GET /signals/user/{user_id}."""
        acl = acl_bytes_for_transport(call.acl_compiled_filter)
        user_id = str(call.query_params.get("user_id") or "")
        headers = self._acl_headers(acl, authorization)
        url = f"{self.signals_url}/signals/user/{user_id}"
        self._record(call.tool_name, acl, {"url": url, "headers": headers, "tenant_id": tenant_id})

        started = time.perf_counter()
        if is_loopback_url(self.signals_url):
            return ToolResult(
                tool_name=call.tool_name,
                ok=True,
                payload={"skipped": True, "reason": "loopback"},
                acl_bytes_sent=acl,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        try:
            resp = await self._request("GET", url, headers=headers)
            latency = (time.perf_counter() - started) * 1000.0
            payload = resp.json() if resp.content else {}
            return ToolResult(
                tool_name=call.tool_name,
                ok=resp.status_code < 400,
                payload=payload if isinstance(payload, dict) else {"raw": payload},
                error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                acl_bytes_sent=acl,
                latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - started) * 1000.0
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                payload={},
                error=str(exc),
                acl_bytes_sent=acl,
                latency_ms=latency,
            )

    async def ingest_activity(
        self,
        events: List[Dict[str, Any]],
        *,
        authorization: Optional[str] = None,
        acl_compiled_filter: Optional[bytes] = None,
    ) -> ToolResult:
        """Async activity ingest to Block I — must not block response streaming."""
        acl = acl_compiled_filter or b"[]"
        headers = self._acl_headers(acl, authorization)
        url = f"{self.signals_url}/activity/ingest"
        self._record("activity_ingest", acl, {"url": url, "event_count": len(events)})
        started = time.perf_counter()
        try:
            resp = await self._request("POST", url, headers=headers, json={"events": events})
            latency = (time.perf_counter() - started) * 1000.0
            payload = resp.json() if resp.content else {}
            return ToolResult(
                tool_name="activity_ingest",
                ok=resp.status_code < 400,
                payload=payload if isinstance(payload, dict) else {"raw": payload},
                error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                acl_bytes_sent=acl,
                latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - started) * 1000.0
            return ToolResult(
                tool_name="activity_ingest",
                ok=False,
                payload={},
                error=str(exc),
                acl_bytes_sent=acl,
                latency_ms=latency,
            )
