"""Live cell widgets + partial updates."""

import io
import json
import zipfile

from PIL import Image

from d200x_button_box import config, layout, protocol, widgets


def test_is_widget_and_interval():
    assert widgets.is_widget({"widget": "clock"}) == "clock"
    assert widgets.is_widget({"widget": "nope"}) is None
    assert widgets.is_widget({"gamepad": 1}) is None
    assert widgets.interval({"widget": "sysload"}) == 2.0
    assert widgets.interval({"widget": "shell", "interval": 9}) == 9.0


def test_render_clock_and_sysload_and_shell():
    for kind in ("clock", "sysload"):
        png = widgets.render({"widget": kind}, (196, 196), dict(layout.DEFAULT_NAV_STYLE))
        assert png and Image.open(io.BytesIO(png)).size == (196, 196)

    png = widgets.render({"widget": "shell", "cmd": "printf 42", "unit": "%"},
                         (196, 196), dict(layout.DEFAULT_NAV_STYLE))
    assert png                                   # renders "42%"
    png = widgets.render({"widget": "shell", "cmd": "exit 1"}, (196, 196),
                         dict(layout.DEFAULT_NAV_STYLE))
    assert png                                   # renders "err", never raises


def _cells(payload):
    z = zipfile.ZipFile(io.BytesIO(payload))
    return set(json.loads(z.read("manifest.json")))


def test_partial_build_is_a_subset():
    pg = config.Page(keys={0: {"gamepad": 1, "label": "A"},
                           13: {"widget": "clock"},
                           3: {"widget": "sysload"}})
    assert set(layout.widget_cells(pg)) == {3, 13}

    full = _cells(layout.build_set_buttons(pg, {}, 0))
    assert len(full) == 14                        # every cell

    part = _cells(layout.build_set_buttons(pg, {}, 0, only={3, 13}))
    assert part == {"3_0", "3_2"}                 # index 3 -> 3_0, status(13) -> 3_2


def test_render_cell_rotation_and_change():
    pg = config.Page(keys={13: {"widget": "clock"}})
    a = layout.render_cell(pg, 13, {}, 0)
    b = layout.render_cell(pg, 13, {}, 180)
    assert a and b and a != b                     # rotated

    # a non-widget cell renders normally through the same path
    pg2 = config.Page(keys={0: {"gamepad": 1, "label": "Pit"}})
    assert layout.render_cell(pg2, 0, {}, 0)


def test_partial_update_opcode():
    assert protocol.CMD_PARTIAL_UPDATE == 0x000D
    pkts = protocol.frame_packets(protocol.CMD_PARTIAL_UPDATE, b"x" * 10)
    assert pkts[0][2:4] == b"\x00\x0d"
