"""Serve the recorded dashboard on loopback with read-only polling."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .dashboard import dashboard_snapshot, render_dashboard


class DashboardServer(ThreadingHTTPServer):
    """Only expose the generated view, never the underlying directory."""

    def __init__(self, source: Path, translations: Path | None, port: int):
        if not 0 <= port <= 65535:
            raise ValueError("dashboard port must be between 0 and 65535")
        self.source = Path(source).resolve()
        self.translations = Path(translations).resolve() if translations else None
        dashboard_snapshot(self.source, self.translations)
        super().__init__(("127.0.0.1", port), DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer
    timeout = 10

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _reply(self, status: int, body: bytes = b"", *, content_type: str = "text/plain",
               etag: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        # Checking the Host blocks DNS rebinding. A different port is allowed for
        # an SSH tunnel whose local and remote ports need not be identical.
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or not re.fullmatch(
            r"(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?", hosts[0].lower()
        ):
            self._reply(403, b"Invalid host")
            return
        if self.path not in ("/", "/api/state"):
            self._reply(404, b"Not found")
            return
        try:
            snapshot = dashboard_snapshot(self.server.source, self.server.translations)
            if self.path == "/":
                body = render_dashboard(snapshot, live=True).encode("utf-8")
                self._reply(200, body, content_type="text/html; charset=utf-8")
                return
            body = json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode("utf-8")
            etag = '"' + hashlib.sha256(body).hexdigest() + '"'
            if self.headers.get("If-None-Match") == etag:
                self._reply(304, etag=etag)
            else:
                self._reply(200, body, content_type="application/json; charset=utf-8", etag=etag)
        except Exception as exc:
            print(f"Dashboard refresh failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            self._reply(503, b"Dashboard snapshot is temporarily unavailable")


def serve_dashboard(source: Path, translations: Path | None = None, port: int = 8765) -> None:
    """Serve until interrupted; the listening socket never leaves loopback."""
    with DashboardServer(source, translations, port) as server:
        print(json.dumps({"dashboard": f"http://127.0.0.1:{server.server_port}/"}), flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
