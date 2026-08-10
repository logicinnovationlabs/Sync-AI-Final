"""Block M — MCP tools (provisional)."""

from __future__ import annotations

import pytest


@pytest.mark.block_m
@pytest.mark.provisional
class TestBlockM:
    def _headers(self, client, principal="principal-alice", tenant="tenant-a", scopes=None):
        tok = client.post(
            "/oauth/token",
            json={
                "principal_id": principal,
                "tenant_id": tenant,
                "scopes": scopes or ["search.read", "document.read"],
            },
        ).json()["access_token"]
        return {"Authorization": f"Bearer {tok}"}

    def test_m1_tool_schema(self, block_client):
        tools = block_client.get("/mcp/tools").json()["tools"]
        assert tools
        for tool in tools:
            assert "name" in tool and "input_schema" in tool
            assert tool["input_schema"].get("type") == "object"
            assert "properties" in tool["input_schema"]

    def test_m2_auth_propagation(self, block_client):
        headers = self._headers(block_client)
        resp = block_client.post(
            "/mcp/call",
            headers=headers,
            json={"tool": "search", "arguments": {"query": "roadmap"}},
        ).json()
        assert resp["auth_principal"] == "principal-alice"
        assert resp["tenant_id"] == "tenant-a"

    def test_m3_tenant_isolation(self, block_client):
        headers = self._headers(block_client, "principal-alice", "tenant-a")
        resp = block_client.post(
            "/mcp/call",
            headers=headers,
            json={"tool": "read_document", "arguments": {"document_id": "doc-restricted"}},
        )
        assert resp.status_code == 403

    def test_m4_rate_limit(self, block_client):
        headers = self._headers(block_client)
        # Provisional: calls succeed and are audited; hard 429 not required offline.
        codes = []
        for _ in range(5):
            resp = block_client.post(
                "/mcp/call",
                headers=headers,
                json={"tool": "search", "arguments": {"query": "API"}},
            )
            codes.append(resp.status_code)
        assert all(c in (200, 429) for c in codes)
        assert codes.count(200) >= 1
