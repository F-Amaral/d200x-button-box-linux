"""HTTP API smoke tests: start the real server against a fake daemon."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from d200x_button_box import api, config


class FakeStore:
    def __init__(self):
        self.active_name = "default"
        self._forced_profile = None


class FakeDaemon:
    def __init__(self, settings):
        self.settings = settings
        self.store = FakeStore()
        self.calls = []
        self._subs = []
        self._httpd = None

    def snapshot(self):
        return {"device": {"connected": True}, "profile": {"name": "default"},
                "profiles": config.list_profiles()}

    def request_reload(self):
        self.calls.append(("reload",))

    def request_profile(self, spec):
        self.calls.append(("profile", spec))

    def request_page(self, spec):
        self.calls.append(("page", spec))

    def subscribe(self, q):
        self._subs.append(q)

    def unsubscribe(self, q):
        self._subs.remove(q)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.yaml")
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path / "profiles")
    config.bootstrap()

    settings = config.Settings.load()
    daemon = FakeDaemon(settings)
    cfg = config.ApiConfig(host="127.0.0.1", port=0)  # port 0 -> ephemeral
    api.Handler.daemon = daemon
    api.Handler.token = None
    httpd = api._Server((cfg.host, cfg.port), api.Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    def call(method, path, body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                payload = r.read()
                return r.status, (payload if raw else json.loads(payload or b"null"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    call.port = port
    yield call, daemon
    httpd.shutdown()


def test_state_and_settings(client):
    call, _ = client
    status, state = call("GET", "/api/state")
    assert status == 200 and state["device"]["connected"] is True

    status, s = call("GET", "/api/settings")
    assert status == 200 and s["gamepad"]["name"] == "D200x Button Box"

    s["device"]["brightness"] = 42
    status, r = call("PUT", "/api/settings", s)
    assert status == 200 and r["ok"] is True
    assert config.Settings.load().brightness == 42


def test_profiles_crud(client):
    call, daemon = client
    status, r = call("GET", "/api/profiles")
    assert status == 200 and "launcher" in r["profiles"]

    status, prof = call("GET", "/api/profiles/lmu")
    assert status == 200 and "keys" in prof or "pages" in prof

    status, r = call("POST", "/api/profiles/testp")
    assert status == 200 and "testp" in config.list_profiles()

    call("PUT", "/api/profiles/testp", {"keys": {"0": {"gamepad": 9, "label": "X"}}})
    assert config.load_profile("testp").page(0).keys[0]["label"] == "X"

    status, r = call("DELETE", "/api/profiles/testp")
    assert status == 200 and "testp" not in config.list_profiles()

    status, _ = call("GET", "/api/profiles/nope")
    assert status == 404


def test_activate_and_page(client):
    call, daemon = client
    call("POST", "/api/activate", {"profile": "lmu"})
    call("POST", "/api/page", {"page": "next"})
    assert ("profile", "lmu") in daemon.calls
    assert ("page", "next") in daemon.calls


def test_static_index(client):
    call, _ = client
    status, body = call("GET", "/", raw=True)
    assert status == 200 and b"D200x" in body


def test_sse_sends_initial_state(client):
    call, daemon = client
    req = urllib.request.Request(f"http://127.0.0.1:{call.port}/api/events")
    lines = []
    with urllib.request.urlopen(req, timeout=3) as r:
        for _ in range(4):
            lines.append(r.readline().decode())
    chunk = "".join(lines)
    assert "connected" in chunk and '"type": "state"' in chunk
