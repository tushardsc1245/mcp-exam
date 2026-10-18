import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EMAIL = "25f1002656@ds.study.iitm.ac.in".strip().lower()  # verify this is your registered email
DEFAULT_PROTOCOL = "2025-03-26"

TOOL = {
    "name": "solve_challenge",
    "description": "Returns the exam challenge response derived from the X-Exam-Challenge header.",
    "inputSchema": {"type": "object", "properties": {}},
}


def answer(challenge: str) -> str:
    return hashlib.sha256(f"{challenge}:{EMAIL}".encode()).hexdigest()[:16]


def handle(msg, headers):
    """Return a JSON-RPC response dict, or None for notifications."""
    method = msg.get("method")
    mid = msg.get("id")
    if mid is None:  # notification (e.g. notifications/initialized)
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code, text):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}

    if method == "initialize":
        proto = (msg.get("params") or {}).get("protocolVersion") or DEFAULT_PROTOCOL
        return ok({
            "protocolVersion": proto,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "exam-mcp", "version": "1.0.0"},
        })
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [TOOL]})
    if method == "tools/call":
        name = (msg.get("params") or {}).get("name")
        if name != "solve_challenge":
            return err(-32602, f"Unknown tool: {name}")
        challenge = headers.get("X-Exam-Challenge", "").strip()
        if not challenge:
            return ok({"content": [{"type": "text", "text": "missing X-Exam-Challenge header"}],
                       "isError": True})
        return ok({"content": [{"type": "text", "text": answer(challenge)}]})
    return err(-32601, f"Method not found: {method}")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS, DELETE")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204)

    def do_GET(self):
        if self.path in ("/", "/health"):
            self._send(200, b"ok", "text/plain")
        else:
            self._send(405)

    def do_DELETE(self):
        self._send(200)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._send(400, json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700, "message": "Parse error"}}).encode())

        if isinstance(data, list):
            out = [r for r in (handle(m, self.headers) for m in data) if r is not None]
            if not out:
                return self._send(202)
            return self._send(200, json.dumps(out).encode())

        resp = handle(data, self.headers)
        if resp is None:
            return self._send(202)
        self._send(200, json.dumps(resp).encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
