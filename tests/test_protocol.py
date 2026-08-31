"""Parser + payload-builder + config checks. Run: pytest -q"""

import io
import json
import struct
import zipfile

from d200x_button_box import config, protocol
from d200x_button_box.layout import build_set_buttons


def _report(cmd, index, marker, act, state=0):
    b = bytearray(64)
    b[0:2] = protocol.HEADER
    struct.pack_into(">H", b, 2, cmd)
    struct.pack_into("<I", b, 4, 4)
    b[8:12] = bytes([state, index, marker, act])
    return bytes(b)


def test_key_press_and_release():
    ev = protocol.parse_input(_report(0x0101, 5, 0, protocol.ACT_PRESS))
    assert (ev.kind, ev.index, ev.action, ev.name) == ("key", 5, "press", "key5")
    assert protocol.parse_input(_report(0x0101, 5, 0, protocol.ACT_RELEASE)).action == "release"


def test_alt_command_id_and_status_key_name():
    ev = protocol.parse_input(_report(0x0102, protocol.STATUS_KEY_INDEX, 0, protocol.ACT_PRESS))
    assert ev.name == "status" and ev.action == "press"


def test_aux_button_names():
    assert protocol.parse_input(_report(0x0101, 15, 0, protocol.ACT_PRESS)).name == "aux_l"
    assert protocol.parse_input(_report(0x0101, 16, 0, protocol.ACT_PRESS)).name == "aux_r"


def test_knob_turn_and_marker():
    assert protocol.parse_input(_report(0x0101, 17, 0, protocol.ACT_TURN_LEFT)).action == "left"
    assert protocol.parse_input(_report(0x0101, 18, 0, protocol.ACT_TURN_RIGHT)).action == "right"
    ev = protocol.parse_input(_report(0x0101, 99, 0x02, protocol.ACT_TURN_RIGHT))
    assert ev.kind == "knob" and ev.action == "right"


def test_non_input_reports_ignored():
    assert protocol.parse_input(_report(protocol.CMD_IN_DEVICE_INFO, 0, 0, 0)) is None
    assert protocol.parse_input(b"") is None


def test_frame_packets_single_and_multi():
    one = protocol.frame_packets(protocol.CMD_SET_BUTTONS, b"hello")
    assert len(one) == 1 and len(one[0]) == protocol.PACKET_SIZE
    assert struct.unpack_from("<I", one[0], 4)[0] == 5
    big = protocol.frame_packets(protocol.CMD_SET_BUTTONS, b"x" * 3000)
    assert len(big) == 3 and all(len(p) == protocol.PACKET_SIZE for p in big)


def test_brightness_and_small_window_shapes():
    assert protocol.build_brightness(150)[8:11] == b"100"
    sw = protocol.build_small_window(1, "12:00:00")
    assert sw[0:2] == protocol.HEADER
    assert struct.unpack_from(">H", sw, 2)[0] == protocol.CMD_SET_SMALL_WINDOW
    assert b"1|0|0|12:00:00|0" in sw


def test_set_buttons_generates_icons_from_labels():
    page = config.Page(keys={
        0: {"gamepad": 1, "label": "TURN L"},
        5: {"gamepad": 6, "label": "Pit"},
        protocol.STATUS_KEY_INDEX: {"label": "STATUS"},
    })
    payload = build_set_buttons(page)
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        manifest = json.loads(z.read("manifest.json"))
        names = z.namelist()
    assert manifest["0_0"]["ViewParam"][0]["Icon"] in names   # generated icon
    assert "Text" not in manifest["0_0"]["ViewParam"][0]
    assert "Icon" not in manifest["3_2"]["ViewParam"][0]       # status = clock only
    for i in range(protocol.PACKET_SIZE - 8, len(payload), protocol.PACKET_SIZE):
        assert payload[i] not in (0x00, 0x7C)


def test_set_buttons_auto_glyph_for_nav():
    page = config.Page(keys={0: {"page": "next"}, 1: {"profile": "home"}})
    payload = build_set_buttons(page)
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        manifest = json.loads(z.read("manifest.json"))
    assert "Icon" in manifest["0_0"]["ViewParam"][0]  # chevron glyph, no label needed
    assert "Icon" in manifest["1_0"]["ViewParam"][0]  # home glyph


def test_set_buttons_embeds_uploaded_icon(tmp_path):
    from PIL import Image

    p = tmp_path / "ic.png"
    Image.new("RGB", (64, 64), "red").save(p)
    payload = build_set_buttons(config.Page(keys={1: {"gamepad": 2, "icon": str(p)}}))
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        names = z.namelist()
        manifest = json.loads(z.read("manifest.json"))
        icon_ref = manifest["1_0"]["ViewParam"][0]["Icon"]
        assert icon_ref in names
        with Image.open(io.BytesIO(z.read(icon_ref))) as img:
            assert img.size == (196, 196)


def test_render_icon_glyph_and_text():
    import io as _io

    from PIL import Image

    from d200x_button_box import glyphs, layout

    g = layout.render_icon({"shape": "round", "mode": "ring", "border": "#ff0000"}, glyph="chevron_right")
    with Image.open(_io.BytesIO(g)) as img:
        assert img.size == (196, 196) and img.mode == "RGBA"
    t = layout.render_icon(None, text="Pit Stop")
    assert isinstance(t, bytes) and t[:8] == b"\x89PNG\r\n\x1a\n"
    assert layout.icon_initials("Traction Control Down") == "TCD"
    assert glyphs.codepoint("next") == glyphs.NAME_TO_CP["chevron_right"]
    assert glyphs.action_glyph({"page": "prev"}) == "prev"
    assert glyphs.label_glyph("Headlights") == "headlights_auto"   # on/off/auto toggle
    assert glyphs.label_glyph("Low Beam") == "hl_low"
    assert glyphs.label_glyph("High Beam Flash") == "hl_high"
    assert glyphs.label_glyph("Wiper Speed") == "wiper"


def test_nav_config_legacy_migration_and_roundtrip():
    from d200x_button_box import config

    # legacy settings.yaml shape -> per-button tap/hold binds
    s = config.Settings.from_raw({
        "nav": {"prev_key": 15, "next_key": 16},
        "home": {"key": 15, "profile": "launcher"},
    })
    assert s.nav.binds[15] == {"tap": "prev_page", "hold": "home"}
    assert s.nav.binds[16] == {"tap": "next_page"}
    assert not hasattr(s.home, "key")

    # new shape round-trips
    back = config.Settings.from_raw(s.to_dict())
    assert back.nav.binds == s.nav.binds

    # a standalone home key (not overlapping a page key) -> tap
    s2 = config.Settings.from_raw({"nav": {"prev_key": 15, "next_key": 16}, "home": {"key": 7}})
    assert s2.nav.binds[7] == {"tap": "home"}


def test_status_strip_modes():
    import io
    import json
    import zipfile

    from PIL import Image

    from d200x_button_box import config, protocol
    from d200x_button_box.layout import STATUS_H, STATUS_W, _cell, build_set_buttons

    def zf(page):
        return zipfile.ZipFile(io.BytesIO(build_set_buttons(page, {})))

    cell = _cell(protocol.STATUS_KEY_INDEX)

    # clock / load -> SmallViewMode 2, no icon (the firmware fills the strip)
    for keys in ({"gamepad": 14}, {"status": "load", "label": "x"}):
        with zf(config.Page(keys={protocol.STATUS_KEY_INDEX: keys})) as z:
            m = json.loads(z.read("manifest.json"))
        assert m[cell]["SmallViewMode"] == 2
        assert "Icon" not in m[cell]["ViewParam"][0]

    # off (custom icon) -> SmallViewMode 2 + a wide 458x196 icon on the 3_2 slot
    with zf(config.Page(keys={protocol.STATUS_KEY_INDEX: {"status": "off", "label": "Radio"}})) as z:
        m = json.loads(z.read("manifest.json"))
        icon = m[cell]["ViewParam"][0]["Icon"]
        assert m[cell]["SmallViewMode"] == 2 and icon
        with Image.open(io.BytesIO(z.read(icon))) as im:
            assert im.size == (STATUS_W, STATUS_H)

    # heartbeat payloads: clock -> mode 1, load -> mode 0, off -> mode 2 (BACKGROUND)
    assert b"1|0|0|12:00:00|0" in protocol.build_small_window(1, "12:00:00")
    assert b"0|42|7||0" in protocol.build_small_window(0, "", 42, 7, 0)
    assert protocol.build_small_window(2, "").startswith(b"\x7c\x7c") and b"2|0|0||0" in protocol.build_small_window(2, "")


def test_send_init_skips_identical_payload():
    from d200x_button_box import config
    from d200x_button_box.device import Device

    dev = Device.__new__(Device)          # bypass hardware open
    writes = []
    dev._write = lambda b: writes.append(b)

    page = config.Page(keys={1: {"gamepad": 2, "label": "Pit"}})
    assert dev.send_init(page, {}) is True
    n = len(writes)
    assert n > 0
    assert dev.send_init(page, {}) is False        # identical -> skipped
    assert len(writes) == n
    assert dev.send_init(page, {}, force=True) is True   # forced re-send
    assert len(writes) > n
    # a real change pushes again
    page.keys[1]["label"] = "Radio"
    assert dev.send_init(page, {}) is True


def test_resolve_key_icon_precedence_and_register():
    from d200x_button_box import layout
    from d200x_button_box.layout import DEFAULT_GAME_STYLE, DEFAULT_NAV_STYLE

    game, nav = dict(DEFAULT_GAME_STYLE), dict(DEFAULT_NAV_STYLE)

    # a shell command / raw keystroke is a "box" control -> nav (neutral) baseline
    assert layout.is_box_binding({"command": "x"})
    assert layout.is_box_binding({"key": "F13"})
    assert not layout.is_box_binding({"gamepad": 3})

    # explicit letters beat an action-derived glyph (command -> terminal)
    a = layout.resolve_key_icon({"command": "x", "icon_text": "CC"}, None, game, nav)
    b = layout.resolve_key_icon({"command": "x"}, None, game, nav)
    assert a and b and a != b               # "CC" text vs the terminal glyph

    # explicit glyph still wins over letters
    c = layout.resolve_key_icon({"glyph": "wiper", "icon_text": "CC"}, None, game, nav)
    d = layout.resolve_key_icon({"glyph": "wiper"}, None, game, nav)
    assert c == d

    # a picked / action-implied glyph carries the label as a caption under it;
    # a label that merely *matched* a glyph by keyword does not
    with_cap = layout.resolve_key_icon({"profile": "lmu", "label": "LMU"}, None, game, nav)
    no_cap = layout.resolve_key_icon({"profile": "lmu"}, None, game, nav)
    assert with_cap and no_cap and with_cap != no_cap
    kw = layout.resolve_key_icon({"gamepad": 1, "label": "Wipers"}, None, game, nav)
    picked = layout.resolve_key_icon({"gamepad": 1, "glyph": "wiper", "label": "Wipers"}, None, game, nav)
    assert kw != picked   # keyword match -> plain icon; explicit pick -> icon + "Wipers"


def test_iso_telltale_render_and_tint():
    import io as _io

    from PIL import Image

    from d200x_button_box import glyphs, layout, telltales

    assert "hl_low" in telltales.names() and "turn" in telltales.names()
    assert "hl_low" in glyphs.telltale_names()

    png = layout.render_icon({"fg": "#ff0000"}, glyph="turn")
    with Image.open(_io.BytesIO(png)) as im:
        im = im.convert("RGBA")
        assert im.size == (196, 196)
        opaque = [im.getpixel((x, y)) for x in range(0, 196, 7) for y in range(0, 196, 7)
                  if im.getpixel((x, y))[3] > 200]
        assert opaque and all(p[0] > 180 and p[1] < 80 and p[2] < 80 for p in opaque)  # tinted red


def test_composed_icons_are_built_and_pickable():
    import io as _io

    from PIL import Image

    from d200x_button_box import compose, glyphs, layout

    # every spec has a committed PNG (run tools/build-composed-icons.py if this fails)
    for name in compose.names():
        assert name in glyphs.telltale_names(), f"{name}.png missing -- rebuild composed icons"
        png = layout.render_icon({"fg": "#4a9eff"}, glyph=name)
        with Image.open(_io.BytesIO(png)) as im:
            assert im.size == (196, 196) and im.mode == "RGBA" and im.getbbox() is not None


def test_compose_render_is_deterministic_and_tinted():
    import io as _io

    from PIL import Image

    from d200x_button_box import compose

    a = compose.render("seat_up", "#ff0000", 128)
    b = compose.render("seat_up", "#ff0000", 128)
    assert a == b
    with Image.open(_io.BytesIO(a)) as im:
        im = im.convert("RGBA")
        px = [im.getpixel((x, y)) for x in range(0, 128, 5) for y in range(0, 128, 5)
              if im.getpixel((x, y))[3] > 200]
        assert px and all(p[0] > 180 and p[1] < 80 and p[2] < 80 for p in px)


def test_render_user_icons_only_missing_and_promote(tmp_path, monkeypatch):
    import os
    import time

    import yaml

    from d200x_button_box import compose

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    assets = tmp_path / "assets"
    (assets / "telltales").mkdir(parents=True)
    monkeypatch.setattr(compose, "_bundled_yaml", lambda: assets / "composed.yaml")
    monkeypatch.setitem(compose.COMPOSED, "seat_fore", compose.COMPOSED["seat_fore"])

    spec = compose.effective_spec("seat_fore")
    spec["base_scale"] = 0.9
    compose.save_user_spec("seat_fore", spec)
    gen = config.user_icons_dir() / "seat_fore.png"
    assert gen.is_file()
    rendered = gen.read_bytes()

    # a newer hand-edited generated PNG survives the startup (only_missing) pass
    gen.write_bytes(b"HANDEDIT")
    os.utime(gen, (time.time() + 10, time.time() + 10))
    compose.render_user_icons(only_missing=True)
    assert gen.read_bytes() == b"HANDEDIT"
    compose.render_user_icons()                      # full pass restores it
    assert gen.read_bytes() == rendered

    png = compose.promote_spec("seat_fore")
    assert png == assets / "telltales" / "seat_fore.png" and png.is_file()
    assert yaml.safe_load((assets / "composed.yaml").read_text())["seat_fore"]["base_scale"] == 0.9
    assert "seat_fore" not in compose.user_specs()   # override cleared
    assert not gen.exists()
    assert compose.effective_spec("seat_fore")["base_scale"] == 0.9  # now the default


def test_settings_roundtrip(tmp_path):
    s = config.Settings(brightness=55, pulse_ms=80, active_profile="lmu")
    s.auto_detect = {"lmu": ["LeMansUltimate"]}
    s.api.port = 9999
    path = tmp_path / "settings.yaml"
    s.save(path)
    back = config.Settings.load(path)
    assert back.brightness == 55 and back.pulse_ms == 80 and back.active_profile == "lmu"
    assert back.auto_detect == {"lmu": ["LeMansUltimate"]} and back.api.port == 9999


def test_default_profile_stable_numbering():
    page = config.default_profile("x").page(0)
    # aux buttons are left unbound (nav system drives them)
    assert set(page.keys) == set(range(13)) | {config.protocol.STATUS_KEY_INDEX}
    assert set(page.knobs) == set(config.KNOB_INDICES)
    # stable map: LCD key i -> button i+1, status -> 14, encoders -> 17..25
    assert page.keys[0]["gamepad"] == 1 and page.keys[12]["gamepad"] == 13
    assert page.keys[13]["gamepad"] == 14
    assert page.knobs[17] == {"left": {"gamepad": 17}, "right": {"gamepad": 18}, "press": {"gamepad": 19}}
    assert page.knobs[19]["right"]["gamepad"] == 24
    nums = [b["gamepad"] for b in page.keys.values() if "gamepad" in b]
    for k in page.knobs.values():
        nums += [k["left"]["gamepad"], k["right"]["gamepad"], k["press"]["gamepad"]]
    assert len(nums) == len(set(nums))


def test_config_dir_env_override(tmp_path):
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-c", "from d200x_button_box import config; print(config.SETTINGS_PATH)"],
        capture_output=True, text=True, env={"D200X_CONFIG_DIR": str(tmp_path / "cfg"), "PATH": ""},
    ).stdout.strip()
    assert out == str(tmp_path / "cfg" / "settings.yaml")


def test_page_style_roundtrip_and_gc(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path / "profiles")
    (tmp_path / "profiles").mkdir()
    (tmp_path / "icons").mkdir()
    (tmp_path / "icons" / "aaaaaaaaaaaaaaaa.png").write_bytes(b"x")   # referenced
    (tmp_path / "icons" / "bbbbbbbbbbbbbbbb.png").write_bytes(b"y")   # orphan

    prof = config.Profile(name="p", pages=[config.Page(
        style={"mode": "ring", "border": "#f00"},
        keys={0: {"gamepad": 1, "icon": str(tmp_path / "icons" / "aaaaaaaaaaaaaaaa.png")}},
    )])
    config.save_profile(prof)
    back = config.load_profile("p")
    assert back.page(0).style == {"mode": "ring", "border": "#f00"}

    removed = config.gc_icons()
    assert removed == 1
    assert (tmp_path / "icons" / "aaaaaaaaaaaaaaaa.png").exists()
    assert not (tmp_path / "icons" / "bbbbbbbbbbbbbbbb.png").exists()


def test_profile_save_load_single_and_multi_page(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path)

    prof = config.default_profile("lmu")
    prof.page(0).keys[0]["label"] = "Ação"
    config.save_profile(prof)
    assert "lmu" in config.list_profiles()
    back = config.load_profile("lmu")
    assert back.n_pages == 1 and back.page(0).keys[0]["label"] == "Ação"

    multi = config.Profile(name="mp", pages=[
        config.Page(name="drive", keys={0: {"gamepad": 1}}),
        config.Page(name="pit", keys={0: {"gamepad": 2}}),
    ])
    config.save_profile(multi)
    r = config.load_profile("mp")
    assert r.n_pages == 2 and r.page(1).name == "pit" and r.page(1).keys[0] == {"gamepad": 2}
