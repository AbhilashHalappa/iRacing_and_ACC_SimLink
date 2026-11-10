"""Loopback HTTP/SSE bridge for the embedded ACC desktop UI.

The bridge only serves built frontend assets and detached snapshots supplied by
the Qt host. It never opens ACC shared memory or decodes telemetry.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import threading
from urllib.parse import urlparse


def _json_default(value):
    """Convert dataclass snapshots (for example acquisition health) to JSON."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class TelemetryBridge:
    def __init__(self, static_root: Path, host: str = "127.0.0.1", port: int = 0) -> None:
        self.static_root = Path(static_root).resolve()
        self._condition = threading.Condition()
        self._snapshot: dict = {"connected": False, "physics": None, "acquisition": {}}
        self._revision = 0
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "RaceEngineerACC/0.1"

            def log_message(self, _format, *_args):
                return

            def _json(self, value: dict, status: int = 200) -> None:
                body = json.dumps(value, separators=(",", ":"), allow_nan=False, default=_json_default).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path == "/api/snapshot":
                    with bridge._condition:
                        snapshot = dict(bridge._snapshot)
                        revision = bridge._revision
                    snapshot["revision"] = revision
                    self._json(snapshot)
                    return
                if path == "/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache, no-transform")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("X-Accel-Buffering", "no")
                    self.end_headers()
                    last_revision = -1
                    try:
                        while True:
                            with bridge._condition:
                                bridge._condition.wait_for(
                                    lambda: bridge._revision != last_revision or bridge._closed,
                                    timeout=10.0,
                                )
                                if bridge._closed:
                                    return
                                snapshot = dict(bridge._snapshot)
                                revision = bridge._revision
                            if revision == last_revision:
                                self.wfile.write(b": keep-alive\n\n")
                            else:
                                snapshot["revision"] = revision
                                payload = json.dumps(snapshot, separators=(",", ":"), allow_nan=False, default=_json_default)
                                self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                                last_revision = revision
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                else:
                    self._serve_asset(path)

            def _serve_asset(self, request_path: str) -> None:
                relative = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
                target = (bridge.static_root / relative).resolve()
                if bridge.static_root not in target.parents and target != bridge.static_root:
                    self._json({"error": "invalid path"}, 400)
                    return
                if not target.is_file():
                    target = bridge.static_root / "index.html"
                if not target.is_file():
                    self._json({"error": "frontend build not found; run npm.cmd run build"}, 404)
                    return
                body = target.read_bytes()
                suffix = target.suffix.lower()
                mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2"}.get(suffix, "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith(("text/", "application/javascript")) else ""))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)

        self._closed = False
        self._server = ThreadingHTTPServer((host, port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name="ACC-Local-Bridge", daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/"

    def start(self) -> str:
        self._thread.start()
        return self.url

    def publish(self, snapshot: dict) -> None:
        # Snapshot is already detached from the acquisition ring and consumer.
        with self._condition:
            self._snapshot = snapshot
            self._revision += 1
            self._condition.notify_all()

    def stop(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._server.shutdown()
        self._server.server_close()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
