"""Serve the recorded dashboard on loopback with read-only polling."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .dashboard import dashboard_snapshot, render_dashboard


def _compact_contexts(snapshot: dict) -> dict:
    """Intern repeated trace text in a freshly created live snapshot."""
    view = snapshot["data"]
    contexts = []
    for row in view.get("candidates", []):
        trace = row.get("optimization_trace") if isinstance(row, dict) else None
        context = trace.get("context") if isinstance(trace, dict) else None
        if isinstance(context, dict):
            contexts.append(context)
    texts = [context.get("text") for context in contexts
             if isinstance(context.get("text"), str) and len(context["text"]) > 1024]
    counts = Counter(texts)
    indexes: dict[str, int] = {}
    pool: list[str] = []
    for context in contexts:
        text = context.get("text")
        if not isinstance(text, str) or counts[text] < 2:
            continue
        if text not in indexes:
            indexes[text] = len(pool)
            pool.append(text)
        context["text"] = {"$context": indexes[text]}
    if pool:
        view["_context_pool"] = pool
    return snapshot


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
               etag: str | None = None, encoding: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Vary", "Accept-Encoding, X-InferRSI-Compact")
        if encoding:
            self.send_header("Content-Encoding", encoding)
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _representation(self, body: bytes) -> tuple[bytes, str | None]:
        for item in self.headers.get("Accept-Encoding", "").split(","):
            name, *parameters = item.split(";")
            if name.strip().lower() != "gzip":
                continue
            quality = 1.0
            for parameter in parameters:
                key, separator, value = parameter.partition("=")
                if separator and key.strip().lower() == "q":
                    try:
                        quality = float(value.strip())
                    except ValueError:
                        quality = 0.0
            if 0 < quality <= 1:
                compressed = gzip.compress(body, compresslevel=3, mtime=0)
                if len(compressed) < len(body):
                    return compressed, "gzip"
        return body, None

    def do_GET(self) -> None:
        # Checking the Host blocks DNS rebinding. A different port is allowed for
        # an SSH tunnel whose local and remote ports need not be identical.
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or not re.fullmatch(
            r"(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?", hosts[0].lower()
        ):
            self._reply(403, b"Invalid host")
            return
        events = re.fullmatch(r"/api/profile-events/([0-9a-f]{64})", self.path)
        if events:
            from .profile_timeline import profile_event_table

            payload = profile_event_table(self.server.source, events.group(1))
            if payload is None:
                self._reply(404, b"No verified profile events")
            else:
                self._reply(200, payload, content_type="application/json", encoding="gzip")
            return
        if self.path not in ("/", "/api/state"):
            self._reply(404, b"Not found")
            return
        try:
            snapshot = dashboard_snapshot(self.server.source, self.server.translations)
            if self.path == "/":
                html = render_dashboard(_compact_contexts(snapshot), live=True)
                body, encoding = self._representation(html.encode("utf-8"))
                self._reply(200, body, content_type="text/html; charset=utf-8", encoding=encoding)
                return
            if self.headers.get("X-InferRSI-Compact") == "1":
                snapshot = _compact_contexts(snapshot)
            body, encoding = self._representation(
                json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode("utf-8")
            )
            etag = '"' + hashlib.sha256(body).hexdigest() + '"'
            if self.headers.get("If-None-Match") == etag:
                self._reply(304, etag=etag, encoding=encoding)
            else:
                self._reply(200, body, content_type="application/json; charset=utf-8", etag=etag,
                            encoding=encoding)
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
