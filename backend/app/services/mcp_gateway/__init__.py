"""Block M: MCP Gateway — in-process module, same FastAPI app and port (§29)."""

from app.services.mcp_gateway.router import router

__all__ = ["router"]
