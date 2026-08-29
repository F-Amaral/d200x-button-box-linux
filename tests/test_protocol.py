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


def test_set_buttons_payload_valid_zip_with_labels():
    payload = build_set_buttons({0: "TURN L", protocol.STATUS_KEY_INDEX: "STATUS"})
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["0_0"]["ViewParam"][0]["Text"] == "TURN L"
    assert manifest["3_2"]["SmallViewMode"] == 2
    assert set(manifest) == {f"{i % 5}_{i // 5}" for i in [*range(13), 13]}
    for i in range(protocol.PACKET_SIZE - 8, len(payload), protocol.PACKET_SIZE):
        assert payload[i] not in (0x00, 0x7C)


def test_set_buttons_embeds_icon(tmp_path):
    from PIL import Image

    p = tmp_path / "ic.png"
    Image.new("RGB", (64, 64), "red").save(p)
    payload = build_set_buttons({}, {1: str(p)})
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        names = z.namelist()
        manifest = json.loads(z.read("manifest.json"))
        icon_ref = manifest["1_0"]["ViewParam"][0]["Icon"]
        assert icon_ref in names
        with Image.open(io.BytesIO(z.read(icon_ref))) as img:
            assert img.size == (196, 196)


def test_settings_roundtrip(tmp_path):
    s = config.Settings(brightness=55, pulse_ms=80, active_profile="lmu")
    s.auto_detect = {"lmu": ["LeMansUltimate"]}
    s.api.port = 9999
    path = tmp_path / "settings.yaml"
    s.save(path)
    back = config.Settings.load(path)
    assert back.brightness == 55 and back.pulse_ms == 80 and back.active_profile == "lmu"
    assert back.auto_detect == {"lmu": ["LeMansUltimate"]} and back.api.port == 9999


def test_default_profile_covers_every_control_uniquely():
    page = config.default_profile("x").page(0)
    assert set(page.keys) == set(config.KEY_INDICES)
    assert set(page.knobs) == set(config.KNOB_INDICES)
    assert page.keys[config.HOME_KEY_INDEX] == {"profile": "home"}   # leftmost aux
    assert page.keys[16] == {"page": "next"}                          # rightmost aux
    nums = [b["gamepad"] for b in page.keys.values() if "gamepad" in b]
    for k in page.knobs.values():
        nums += [k["left"]["gamepad"], k["right"]["gamepad"], k["press"]["gamepad"]]
    assert len(nums) == len(set(nums))


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
