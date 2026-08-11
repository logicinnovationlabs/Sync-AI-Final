"""Minimal Block C ACL mock for Phase 2 local compose."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# In-memory allow set: "tenant|doc|principal"
ALLOWED: set[str] = set()


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "bad json"})
            return

        if self.path == "/acl/compile":
            key = f"{data.get('tenant_id')}|{data.get('document_id')}|{data.get('principal_id')}"
            self._json(200, {"allowed": key in ALLOWED, "decision": "allow" if key in ALLOWED else "deny"})
            return

        if self.path == "/acl/grant":
            key = f"{data.get('tenant_id')}|{data.get('document_id')}|{data.get('principal_id')}"
            ALLOWED.add(key)
            self._json(200, {"ok": True})
            return

        if self.path == "/acl/revoke":
            key = f"{data.get('tenant_id')}|{data.get('document_id')}|{data.get('principal_id')}"
            ALLOWED.discard(key)
            self._json(200, {"ok": True})
            return

        self._json(404, {"error": "not found"})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8001), Handler)
    print("ACL mock listening on :8001", flush=True)
    server.serve_forever()
