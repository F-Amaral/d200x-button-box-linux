"""Self-check for the report parser and the default config. Run: pytest -q"""

import struct

import yaml

from d200x_button_box import protocol
from d200x_button_box.config import Config, default_yaml


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
    ev = protocol.parse_input(_report(0x0101, 5, 0, protocol.ACT_RELEASE))
    assert ev.action == "release"


def test_alt_command_id_and_status_key_name():
    ev = protocol.parse_input(_report(0x0102, protocol.STATUS_KEY_INDEX, 0, protocol.ACT_PRESS))
    assert ev.name == "status" and ev.action == "press"


def test_knob_turn_recognised_by_index():
    ev = protocol.parse_input(_report(0x0101, 17, 0, protocol.ACT_TURN_LEFT))
    assert (ev.kind, ev.action, ev.name) == ("knob", "left", "knob17")
    ev = protocol.parse_input(_report(0x0101, 19, 0, protocol.ACT_TURN_RIGHT))
    assert ev.action == "right"


def test_knob_recognised_by_marker_byte():
    ev = protocol.parse_input(_report(0x0101, 99, 0x02, protocol.ACT_TURN_RIGHT))
    assert ev.kind == "knob" and ev.action == "right"


def test_non_input_reports_ignored():
    assert protocol.parse_input(_report(protocol.CMD_IN_DEVICE_INFO, 0, 0, 0)) is None
    assert protocol.parse_input(b"\x00\x01\x02") is None
    assert protocol.parse_input(b"") is None


def test_brightness_packet_shape():
    pkt = protocol.build_brightness(150)  # clamps to 100
    assert len(pkt) == protocol.PACKET_SIZE
    assert pkt[0:2] == protocol.HEADER
    assert struct.unpack_from(">H", pkt, 2)[0] == protocol.CMD_SET_BRIGHTNESS
    assert pkt[8:11] == b"100"


def test_default_config_covers_every_control():
    d = yaml.safe_load(default_yaml())
    expected = set(range(13)) | {protocol.STATUS_KEY_INDEX} | set(protocol.PAGE_KEY_INDICES)
    assert set(d["keys"]) == expected
    assert set(d["knobs"]) == set(protocol.KNOB_INDICES)
    # every gamepad button number is unique
    nums = [b["gamepad"] for b in d["keys"].values()]
    for k in d["knobs"].values():
        nums += [k["left"]["gamepad"], k["right"]["gamepad"], k["press"]["gamepad"]]
    assert len(nums) == len(set(nums))


def test_config_load_missing_file_is_defaults(tmp_path):
    c = Config.load(tmp_path / "nope.yaml")
    assert c.gamepad_buttons == 32 and c.keys == {} and c.knobs == {}


def test_aux_button_names():
    ev = protocol.parse_input(_report(0x0101, 15, 0, protocol.ACT_PRESS))
    assert ev.name == "aux_l" and ev.kind == "key"
    ev = protocol.parse_input(_report(0x0101, 16, 0, protocol.ACT_PRESS))
    assert ev.name == "aux_r"


def test_frame_packets_single_and_multi():
    one = protocol.frame_packets(protocol.CMD_SET_BUTTONS, b"hello")
    assert len(one) == 1 and len(one[0]) == protocol.PACKET_SIZE
    assert one[0][0:2] == protocol.HEADER
    assert struct.unpack_from("<I", one[0], 4)[0] == 5

    big = protocol.frame_packets(protocol.CMD_SET_BUTTONS, b"x" * 3000)
    assert len(big) == 3  # 1016 + 1024 + rest
    assert all(len(p) == protocol.PACKET_SIZE for p in big)


def test_set_buttons_payload_is_valid_zip_with_manifest():
    import io
    import json
    import zipfile

    from d200x_button_box.layout import build_set_buttons

    payload = build_set_buttons({0: "TURN L", protocol.STATUS_KEY_INDEX: "STATUS"})
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["0_0"]["ViewParam"][0]["Text"] == "TURN L"
    assert manifest["3_2"]["SmallViewMode"] == 2          # status slot -> idx 13
    assert set(manifest) == {f"{i % 5}_{i // 5}" for i in [*range(13), 13]}
    # first byte of every post-first 1024-chunk must dodge the firmware bug
    for i in range(protocol.PACKET_SIZE - 8, len(payload), protocol.PACKET_SIZE):
        assert payload[i] not in (0x00, 0x7C)
