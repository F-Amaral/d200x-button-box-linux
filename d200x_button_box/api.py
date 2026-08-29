"""Local HTTP + SSE control API for the daemon. Stdlib only.

Started by ``d200x-buttonboxd`` unless ``--no-api``. Persistent changes go
through the config files (the daemon's mtime poll picks them up); transient
actions (activate a profile without saving, switch page) go through in-memory
requests. ``GET /api/events`` is a Server-Sent-Events stream of input + state
changes, used by the web UI's "press a key to bind" flow.

Endpoints
---------
    GET  /api/state
    GET  /api/settings                 PUT /api/settings          {full dict}
    GET  /api/profiles
    GET  /api/profiles/<name>          PUT /api/profiles/<name>   {pages|keys/knobs}
    POST /api/profiles/<name>          (create from default if missing)
    DELETE /api/profiles/<name>
    POST /api/activate                 {"profile": "<name>|auto"}
    POST /api/page                     {"page": "next"|"prev"|<int>}
    GET  /api/events                   (SSE)
    GET  /...                          static files from webui/
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config

log = logging.getLogger(__name__)

WEBUI_DIR = Path(__file__).parent / "webui"
_CTYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript",
    ".css": "text/css",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".ico": "image/x-icon",
}


def serve(daemon, api_cfg) -> threading.Thread | None:
    Handler.daemon = daemon
    Handler.token = api_cfg.token
    try:
        httpd = _Server((api_cfg.host, api_cfg.port), Handler)
    except OSError as e:
        log.warning("API disabled: cannot bind %s:%s (%s)", api_cfg.host, api_cfg.port, e)
        return None
    daemon._httpd = httpd
    t = threading.Thread(target=httpd.serve_forever, name="d200x-api", daemon=True)
    t.start()
    log.info("API on http://%s:%s", api_cfg.host, api_cfg.port)
    return t


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    daemon = None
    token = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):  # keep the daemon log clean
        pass

    # -- dispatch --------------------------------------------------------
    def do_GET(self):
        self._route("GET")

    def do_PUT(self):
        self._route("PUT")

    def do_POST(self):
        self._route("POST")

    def do_DELETE(self):
        self._route("DELETE")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _route(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            if not self._authed(parsed.query):
                return self._json({"error": "unauthorized"}, 401)
            try:
                return self._api(method, path)
            except FileNotFoundError:
                return self._json({"error": "not found"}, 404)
            except (ValueError, KeyError, TypeError) as e:
                return self._json({"error": f"bad request: {e}"}, 400)
            except Exception as e:  # noqa: BLE001
                log.exception("api %s %s failed", method, path)
                return self._json({"error": str(e)}, 500)
        if method == "GET":
            return self._static(path)
        self._json({"error": "not found"}, 404)

    # -- helpers --------------------------------------------------------
    def _authed(self, qs: str) -> bool:
        if not self.token:
            return True
        got = self.headers.get("X-Token") or parse_qs(qs).get("token", [None])[0]
        return got == self.token

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Token")

    def _json(self, obj, status: int = 200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        return json.loads(raw) if raw else {}

    # -- API ----------------------------------------------------------
    def _api(self, method: str, path: str):
        d = self.daemon
        seg = path.strip("/").split("/")[1:]  # drop "api"

        if seg == ["state"] and method == "GET":
            return self._json(d.snapshot())

        if seg == ["settings"]:
            if method == "GET":
                return self._json(d.settings.to_dict())
            if method == "PUT":
                config.write_settings_dict(self._read_body())
                d.request_reload()
                return self._json({"ok": True})

        if seg == ["profiles"] and method == "GET":
            return self._json({"profiles": config.list_profiles(), "active": d.store.active_name})

        if len(seg) == 2 and seg[0] == "profiles":
            name = seg[1]
            if method == "GET":
                if name not in config.list_profiles():
                    raise FileNotFoundError(name)
                return self._json(config.load_profile(name).to_dict())
            if method == "PUT":
                config.write_profile_dict(name, self._read_body())
                d.request_reload()
                return self._json({"ok": True})
            if method == "POST":
                if name not in config.list_profiles():
                    config.save_profile(config.default_profile(name))
                return self._json({"ok": True, "created": True})
            if method == "DELETE":
                return self._json({"ok": config.delete_profile(name)})

        if seg == ["activate"] and method == "POST":
            d.request_profile(str(self._read_body().get("profile") or "auto"))
            return self._json({"ok": True})

        if seg == ["page"] and method == "POST":
            d.request_page(str(self._read_body().get("page", "next")))
            return self._json({"ok": True})

        if seg == ["events"] and method == "GET":
            return self._sse()

        return self._json({"error": "not found"}, 404)

    def _sse(self):
        q: queue.Queue = queue.Queue(maxsize=256)
        self.daemon.subscribe(q)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()
        try:
            self._sse_write(b": connected\n\n")
            self._sse_write(f"data: {json.dumps({'type': 'state', **self.daemon.snapshot()})}\n\n".encode())
            while True:
                try:
                    ev = q.get(timeout=15)
                    self._sse_write(f"data: {json.dumps(ev)}\n\n".encode())
                except queue.Empty:
                    self._sse_write(b": ping\n\n")
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.daemon.unsubscribe(q)

    def _sse_write(self, chunk: bytes):
        self.wfile.write(chunk)
        self.wfile.flush()

    # -- static -----------------------------------------------------
    def _static(self, path: str):
        root = WEBUI_DIR.resolve()
        target = (root / path.lstrip("/")).resolve()
        inside = target == root or root in target.parents
        if not inside or not target.is_file():
            target = root / "index.html"  # SPA fallback
        if not target.is_file():
            return self._json({"error": "web UI not built yet"}, 404)
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _CTYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)
