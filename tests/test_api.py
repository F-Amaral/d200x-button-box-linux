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

    def force_profile(self, name):
        self._forced_profile = name


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

    def request_repush(self):
        self.calls.append(("repush",))

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


def test_token_auth_header_query_and_cookie(client, monkeypatch):
    call, _ = client
    monkeypatch.setattr(api.Handler, "token", "s3cr3t")
    try:
        base = f"http://127.0.0.1:{call.port}"

        def get(headers=None, qs=""):
            req = urllib.request.Request(base + "/api/state" + qs, headers=headers or {})
            try:
                with urllib.request.urlopen(req, timeout=3) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code

        assert get() == 401
        assert get(headers={"X-Token": "s3cr3t"}) == 200
        assert get(qs="?token=s3cr3t") == 200
        assert get(headers={"Cookie": "d200x_token=s3cr3t; other=x"}) == 200
        assert get(headers={"X-Token": "wrong"}) == 401
        # static files stay open so the page can load and read the token
        req = urllib.request.Request(base + "/")
        with urllib.request.urlopen(req, timeout=3) as r:
            assert r.status == 200
    finally:
        api.Handler.token = None


def test_state_and_settings(client):
    call, _ = client
    status, state = call("GET", "/api/state")
    assert status == 200 and state["device"]["connected"] is True

    status, s = call("GET", "/api/settings")
    assert status == 200 and s["gamepad"]["name"] == "D200x Button Box"

    s["device"]["brightness"] = 42
    s["device"]["orientation"] = 180
    status, r = call("PUT", "/api/settings", s)
    assert status == 200 and r["ok"] is True
    loaded = config.Settings.load()
    assert loaded.brightness == 42 and loaded.orientation == 180
    assert loaded.to_dict()["device"]["orientation"] == 180


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


def test_profile_rename_and_duplicate(client):
    call, _ = client
    call("POST", "/api/profiles/src")
    call("PUT", "/api/profiles/src", {"keys": {"0": {"gamepad": 4, "label": "Y"}}})

    status, r = call("POST", "/api/profiles/src/duplicate", {"to": "copy"})
    assert status == 200 and r["name"] == "copy"
    assert config.load_profile("copy").page(0).keys[0]["label"] == "Y"

    status, r = call("POST", "/api/profiles/src/rename", {"to": "renamed"})
    assert status == 200 and r["name"] == "renamed"
    assert "src" not in config.list_profiles() and "renamed" in config.list_profiles()

    status, r = call("POST", "/api/profiles/renamed/rename", {"to": "copy"})
    assert status == 409                                   # target exists

    status, r = call("POST", "/api/profiles/ghost/rename", {"to": "x"})
    assert status == 404


def test_delete_active_profile_falls_back_to_home(client):
    call, daemon = client
    from d200x_button_box import config
    call("POST", "/api/profiles/gone")
    s = config.Settings.load()
    s.active_profile = "gone"
    s.save()
    daemon.settings = s
    daemon.store._forced_profile = "gone"

    status, r = call("DELETE", "/api/profiles/gone")
    assert status == 200
    assert r["active"] == s.home.profile
    assert config.Settings.load().active_profile == s.home.profile
    assert daemon.store._forced_profile is None
    assert "gone" not in config.list_profiles()

    # the home profile itself is protected
    home = config.Settings.load().home.profile
    status, r = call("DELETE", f"/api/profiles/{home}")
    assert status == 409 and home in config.list_profiles()


def test_profile_game_field_roundtrips(client):
    call, _ = client
    call("POST", "/api/profiles/withgame")
    call("PUT", "/api/profiles/withgame", {"game": "ac_rally", "keys": {"0": {"gamepad": 1}}})
    from d200x_button_box import config
    assert config.load_profile("withgame").game == "ac_rally"
    status, prof = call("GET", "/api/profiles/withgame")
    assert prof["game"] == "ac_rally"


def test_games_endpoint(client):
    call, _ = client
    status, games = call("GET", "/api/games")
    assert status == 200 and "lmu" in games and "path" in games["lmu"]
    assert games["lmu"]["can_read"] and games["lmu"]["can_write"]
    assert games["ac_rally"]["can_read"] and games["ac_rally"]["can_write"]
    assert games["ac_evo"]["can_read"] and games["ac_evo"]["can_write"]


def test_glyphs_endpoint(client):
    call, _ = client
    status, g = call("GET", "/api/glyphs")
    assert status == 200
    assert "wiper" in g["telltales"]            # the dashboard/ISO set for the picker
    assert "home" in g["material"]              # curated Material set, name -> codepoint hex
    assert int(g["material"]["home"], 16) > 0
    assert "seat_fore" in g["composed"]


def test_import_endpoint(client, tmp_path):
    import json as _json

    call, daemon = client
    lmu = tmp_path / "lmu"
    (lmu / "UserData" / "player").mkdir(parents=True)
    (lmu / "UserData" / "player" / "direct input.json").write_text(_json.dumps({
        "Devices": {"D200x Button Box-A": {}},
        "Input": {"Headlights": {"device": "D200x Button Box-A", "id": 32}},
    }))
    # default profile has key 0 -> gamepad 1
    status, rep = call("POST", "/api/profiles/default/import", {"game": "lmu", "path": str(lmu)})
    assert status == 200
    assert rep["applied"] == {"1": "Headlights"}
    assert rep["created"] is False
    assert config.load_profile("default").page(0).keys[0]["label"] == "Headlights"
    assert ("reload",) in daemon.calls

    # importing into a name that doesn't exist creates it from the stable map
    status, rep = call("POST", "/api/profiles/lmu-2/import", {"game": "lmu", "path": str(lmu)})
    assert status == 200 and rep["created"] is True and rep["profile"] == "lmu-2"
    assert "lmu-2" in config.list_profiles()
    p2 = config.load_profile("lmu-2").page(0)
    assert p2.keys[0]["label"] == "Headlights"
    # the full button map is kept (not pruned), just unlabeled
    assert p2.keys[5] == {"gamepad": 6}
    assert p2.knobs


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


def test_icon_upload_and_fetch(client, tmp_path):
    import io

    from PIL import Image

    call, _ = client
    buf = io.BytesIO()
    Image.new("RGB", (32, 48), "green").save(buf, format="PNG")

    req = urllib.request.Request(
        f"http://127.0.0.1:{call.port}/api/icons", data=buf.getvalue(),
        method="POST", headers={"Content-Type": "image/png"},
    )
    with urllib.request.urlopen(req, timeout=3) as r:
        res = json.loads(r.read())
    assert res["url"].startswith("/api/icons/") and res["path"].endswith(".png")

    status, png = call("GET", res["url"], raw=True)
    assert status == 200
    assert Image.open(io.BytesIO(png)).size == (196, 196)


def test_compose_editor_roundtrip(client, tmp_path):
    import io

    from PIL import Image

    from d200x_button_box import compose, telltales

    call, daemon = client

    # built-ins are listed, none customised yet
    status, all_specs = call("GET", "/api/compose")
    assert status == 200 and all_specs["seat_fore"]["builtin"] is True
    assert all_specs["seat_fore"]["customised"] is False

    # preview renders without saving
    spec = compose.effective_spec("seat_fore")
    spec["layers"][0]["at"] = [0.54, 0.80]  # nudge the arrow down
    status, png = call("POST", "/api/compose/preview", {"spec": spec}, raw=True)
    assert status == 200 and Image.open(io.BytesIO(png)).size == (256, 256)
    assert not compose._user_yaml().exists()

    # save -> icons.yaml written, PNG rendered, deck re-push requested
    status, res = call("PUT", "/api/compose/seat_fore", {"spec": spec})
    assert status == 200 and res["ok"] is True
    assert ("repush",) in daemon.calls
    assert compose.user_specs()["seat_fore"]["layers"][0]["at"] == [0.54, 0.80]
    gen = config.user_icons_dir() / "seat_fore.png"
    assert gen.is_file()
    assert telltales._path("seat_fore") == gen  # resolver now prefers it

    # a new user icon with a coloured layer -> the colour survives a key tint
    coloured = {"base": "turn", "base_scale": 1.0, "base_at": [0.5, 0.5], "layers": [
        {"type": "arrow", "at": [0.62, 0.5], "dir": "left", "len": 0.34, "head": 0.13,
         "w": 0.06, "color": "#4a9eff"}]}
    call("PUT", "/api/compose/turn_left", {"spec": coloured})
    assert "turn_left" in call("GET", "/api/compose")[1]
    tinted = telltales.tint("turn_left", "#ff0000", 96)   # fg red
    im = Image.open(io.BytesIO(tinted)).convert("RGBA")
    px = im.load()
    red = blue = 0
    for y in range(0, 96, 3):
        for x in range(0, 96, 3):
            r, g, b, a = px[x, y]
            if a < 20:
                continue
            if r > 150 and g < 100 and b < 100:
                red += 1
            elif b > 150 and r < 120:
                blue += 1
    assert red > 10 and blue > 10  # base recoloured, the arrow kept its blue

    # a region layer: fill the left arrow's enclosed interior white, keep the rest
    region = {"base": "turn", "base_scale": 1.0, "base_at": [0.5, 0.5], "layers": [
        {"type": "region", "at": [0.25, 0.5], "size": [0.5, 1.0], "color": "#4a9eff", "fill": "#ffffff"}]}
    _, png2 = call("POST", "/api/compose/preview", {"spec": region, "fg": "#cccccc"}, raw=True)
    im2 = Image.open(io.BytesIO(png2)).convert("RGBA")
    p2 = im2.load()
    W, H = im2.size
    white = grey = 0
    for y in range(0, H, 3):
        for x in range(0, W, 3):
            r, g, b, a = p2[x, y]
            if a < 20:
                continue
            if min(r, g, b) > 230:
                white += 1
            elif 180 < r < 220 and abs(r - g) < 15 and abs(g - b) < 15:
                grey += 1
    assert white > 20 and grey > 20  # left arrow filled white, right arrow still grey

    status, one = call("GET", "/api/compose/seat_fore")
    assert one["customised"] is True

    # reset -> override + PNG gone
    status, _ = call("DELETE", "/api/compose/seat_fore")
    assert status == 200
    assert "seat_fore" not in compose.user_specs()
    assert not gen.exists()


def test_action_icons_endpoint(client):
    call, daemon = client
    from d200x_button_box import glyphs

    status, m = call("GET", "/api/action-icons")
    assert status == 200 and m == {}

    call("PUT", "/api/action-icons", {"label": "Cycle Lights", "glyph": "fog_front"})
    assert glyphs.label_glyph("cycle lights") == "fog_front"          # exact override wins
    assert glyphs.label_glyph("Cycle Wipers") == "wiper"              # others still keyword-matched
    assert ("repush",) in daemon.calls

    call("PUT", "/api/action-icons", {"label": "Cycle Lights", "glyph": None})
    assert glyphs.label_glyph("cycle lights") == "headlights_auto"    # back to the keyword hint


def test_sse_sends_initial_state(client):
    call, daemon = client
    req = urllib.request.Request(f"http://127.0.0.1:{call.port}/api/events")
    lines = []
    with urllib.request.urlopen(req, timeout=3) as r:
        for _ in range(4):
            lines.append(r.readline().decode())
    chunk = "".join(lines)
    assert "connected" in chunk and '"type": "state"' in chunk
