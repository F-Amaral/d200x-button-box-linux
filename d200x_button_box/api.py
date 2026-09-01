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


def serve(daemon, api_cfg) -> None:
    Handler.daemon = daemon
    Handler.token = api_cfg.token
    try:
        httpd = _Server((api_cfg.host, api_cfg.port), Handler)
    except OSError as e:
        log.warning("API disabled: cannot bind %s:%s (%s)", api_cfg.host, api_cfg.port, e)
        return
    daemon._httpd = httpd
    threading.Thread(target=httpd.serve_forever, name="d200x-api", daemon=True).start()
    log.info("API on http://%s:%s", api_cfg.host, api_cfg.port)


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _save_icon(data: bytes) -> dict:
    """Normalise an uploaded image to a 196x196 PNG under CONFIG_DIR/icons/."""
    import hashlib
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGBA")
        if img.size != (196, 196):
            img = img.resize((196, 196), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
    png = buf.getvalue()
    name = hashlib.sha1(png).hexdigest()[:16] + ".png"
    dest = config.upload_icons_dir() / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(png)
    return {"path": str(dest), "url": f"/api/icons/{name}"}


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
        raw = self._read_raw_body()
        return json.loads(raw) if raw else {}

    def _read_raw_body(self) -> bytes:
        n = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(n) if n else b""

    def _raw(self, data: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

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

        if seg == ["games"] and method == "GET":
            from . import games

            merged = {k: {"path": d.settings.games.get(k) or info["path"],
                          "label": info["label"],
                          "can_read": info["can_read"], "can_write": info["can_write"]}
                      for k, info in games.available().items()}
            for k, p in d.settings.games.items():
                merged.setdefault(k, {"path": p, "label": k.upper(), "can_read": False, "can_write": False})
            return self._json(merged)

        if len(seg) == 3 and seg[0] == "games" and seg[2] == "controls" and method == "GET":
            from . import games

            game = seg[1]
            path = d.settings.games.get(game) or (games.available().get(game) or {}).get("path")
            if not path:
                return self._json({"error": f"no install path for {game}"}, 400)
            return self._json(games.controls(game, path))

        if len(seg) == 3 and seg[0] == "games" and seg[2] == "bind" and method == "POST":
            from . import gamedetect, games

            game, body = seg[1], self._read_body()
            path = body.get("path") or d.settings.games.get(game) or (games.available().get(game) or {}).get("path")
            if not path:
                return self._json({"error": f"no install path for {game}"}, 400)
            needles = d.settings.auto_detect.get(game)
            if needles and gamedetect.detect({game: needles}):
                return self._json({"error": f"{game} is running -- close it first (it reads its config at startup)"}, 409)
            control = body["control"]
            button = None if body.get("clear") else int(body["button"])
            return self._json(games.bind(game, path, control, button))

        if seg == ["profiles"] and method == "GET":
            names = config.list_profiles()
            linked = {}
            for n in names:
                try:
                    g = config.load_profile(n).game
                    if g:
                        linked[n] = g
                except Exception:  # noqa: BLE001
                    pass
            return self._json({"profiles": names, "active": d.store.active_name, "games": linked})

        if len(seg) == 3 and seg[0] == "profiles" and seg[2] == "import" and method == "POST":
            from . import gameimport, games

            name, body = seg[1], self._read_body()
            game = body.get("game", "lmu")
            path = body.get("path") or d.settings.games.get(game) or (games.available().get(game) or {}).get("path")
            if not path:
                return self._json({"error": f"no install path for {game}"}, 400)
            created = name not in config.list_profiles()
            prof = config.default_profile(name) if created else config.load_profile(name)
            report = gameimport.apply_labels(
                prof, games.read(game, path), overwrite=body.get("overwrite", True))
            if created:
                # a new game profile carries only what the game actually binds
                keep = {int(b) for b in (*report["applied"], *report["skipped"])}
                gameimport.prune_to_buttons(prof, keep)
            prof.game = game
            config.save_profile(prof)
            if created:
                s = d.settings
                s.games.setdefault(game, str(path))
                hints = games.detect_hints().get(game)
                # canonical "<game>" profile also gets the auto-detect rule
                if name == game and game not in s.auto_detect and hints:
                    s.auto_detect[name] = list(hints)
                s.save()
            d.request_reload()
            return self._json({**report, "created": created, "profile": name})

        if len(seg) == 3 and seg[0] == "profiles" and seg[2] in ("rename", "duplicate") and method == "POST":
            old, action = seg[1], seg[2]
            to = str((self._read_body().get("to") or "")).strip()
            if not to:
                return self._json({"error": "missing 'to'"}, 400)
            try:
                new = (config.rename_profile if action == "rename"
                       else config.duplicate_profile)(old, to)
            except FileNotFoundError:
                raise FileNotFoundError(old)
            except FileExistsError as e:
                return self._json({"error": f"'{e}' already exists"}, 409)
            if action == "rename":
                s = d.settings
                touched = False
                if s.active_profile == old:
                    s.active_profile = new; touched = True
                if s.home.profile == old:
                    s.home.profile = new; touched = True
                if touched:
                    s.save()
                if d.store._forced_profile == old:
                    d.store.force_profile(new)
            config.gc_icons()
            d.request_reload()
            return self._json({"ok": True, "name": new})

        if len(seg) == 2 and seg[0] == "profiles":
            name = seg[1]
            if method == "GET":
                if name not in config.list_profiles():
                    raise FileNotFoundError(name)
                return self._json(config.load_profile(name).to_dict())
            if method == "PUT":
                config.write_profile_dict(name, self._read_body())
                config.gc_icons()
                d.request_reload()
                return self._json({"ok": True})
            if method == "POST":
                if name not in config.list_profiles():
                    src = str((self._read_body().get("copy_from") or "")).strip()
                    if src and src in config.list_profiles():
                        config.duplicate_profile(src, name)
                    else:
                        config.save_profile(config.default_profile(name))
                return self._json({"ok": True, "created": True})
            if method == "DELETE":
                s = d.settings
                if name == s.home.profile:
                    return self._json({"error": "the home profile can't be deleted"}, 409)
                ok = config.delete_profile(name)
                if ok:
                    if s.active_profile == name:
                        s.active_profile = s.home.profile   # fall back to home
                        s.save()
                    if getattr(d.store, "_forced_profile", None) == name:
                        d.store.force_profile(None)
                config.gc_icons()
                d.request_reload()
                return self._json({"ok": ok, "active": s.active_profile})

        if seg == ["icon-preview"] and method == "GET":
            from . import glyphs, layout

            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            style = {k: q[k] for k in layout.STYLE_KEYS if k in q}
            glyph = q.get("glyph") or (glyphs.label_glyph(q["label"]) if q.get("label") else None)
            size = None
            if q.get("w") and q.get("h"):
                size = (int(q["w"]), int(q["h"]))
            return self._raw(layout.render_icon(
                style, q.get("text") or q.get("label", ""), glyph, q.get("caption", ""), size), "image/png")

        if seg == ["action-icons"]:
            from . import glyphs

            if method == "GET":
                return self._json(glyphs.action_icon_map())
            if method == "PUT":
                body = self._read_body()
                glyphs.set_action_icon(body["label"], body.get("glyph") or None)
                d.request_repush()
                return self._json({"ok": True})

        if seg == ["glyphs"] and method == "GET":
            from . import compose, glyphs, telltales

            # for the symbol picker + compose base list: our dashboard/ISO set,
            # the curated Material set (name -> codepoint hex, for @font-face),
            # and which of them are parametric composed icons.
            return self._json({
                "telltales": telltales.names(),
                "material": {k: f"{v:x}" for k, v in glyphs.NAME_TO_CP.items()},
                "composed": list(compose.all_specs()),
            })

        # --- icon editor: parametric composed icons -----------------
        if seg == ["compose"] and method == "GET":
            from . import compose

            return self._json(compose.all_specs())

        if seg == ["compose", "preview"] and method == "POST":
            from . import compose

            body = self._read_body()
            spec = body.get("spec", body)
            return self._raw(compose.render(spec, body.get("fg", "#ffffff"), 256), "image/png")

        if len(seg) == 2 and seg[0] == "compose":
            from . import compose

            name = seg[1]
            if method == "GET":
                specs = compose.all_specs()
                if name not in specs:
                    raise FileNotFoundError(name)
                return self._json(specs[name])
            if method == "PUT":
                body = self._read_body()
                compose.save_user_spec(name, body.get("spec", body))
                d.request_repush()
                return self._json({"ok": True})
            if method == "DELETE":
                compose.save_user_spec(name, None)
                d.request_repush()
                return self._json({"ok": True})

        if seg == ["font"] and method == "GET":
            from . import glyphs

            return self._raw(glyphs.FONT_PATH.read_bytes(), "font/otf")

        if seg == ["icons"] and method == "POST":
            return self._json(_save_icon(self._read_raw_body()))
        if len(seg) == 2 and seg[0] == "icons" and method == "GET":
            base = config.upload_icons_dir().resolve()
            f = (base / seg[1]).resolve()
            if base in f.parents and f.is_file():
                return self._raw(f.read_bytes(), "image/png")
            raise FileNotFoundError(seg[1])

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
