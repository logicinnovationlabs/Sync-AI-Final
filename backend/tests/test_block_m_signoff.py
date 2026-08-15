"""Block M MCP gateway — contract exists, implementation is not in this monolith."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _get_app

pytestmark = pytest.mark.block_m


def test_m1_mcp_tools_route_not_shipped_yet():
    """GET /mcp/tools is in contracts/mcp-contract.yaml but not mounted on the app."""
    client = TestClient(_get_app())
    resp = client.get("/mcp/tools")
    resp_v1 = client.get("/api/v1/mcp/tools")
    assert resp.status_code == 404
    assert resp_v1.status_code == 404
    pytest.skip(
        "Block M MCP gateway is not implemented. "
        "Contract: contracts/mcp-contract.yaml (GET /mcp/tools, POST /mcp/call)."
    )


def test_m2_mcp_call_route_not_shipped_yet():
    client = TestClient(_get_app())
    resp = client.post("/mcp/call", json={})
    assert resp.status_code in (404, 405, 422)
    pytest.skip("Block M POST /mcp/call is not implemented.")
