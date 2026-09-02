"""Physical rotation: logical <-> physical remap + icon placement."""

import io
import json
import zipfile

from PIL import Image

from d200x_button_box import config, layout, orient, protocol


def test_identity_at_zero():
    for i in range(20):
        assert orient.to_physical(i, 0) == i
        assert orient.to_logical(i, 0) == i
    assert orient.icon_degrees(0) == 0


def test_180_is_an_involution():
    for i in [*range(13), 13, 15, 16, 17, 18, 19]:
        assert orient.to_logical(orient.to_physical(i, 180), 180) == i


def test_180_remap():
    assert orient.to_physical(0, 180) == 12      # LCD keys reverse
    assert orient.to_physical(12, 180) == 0
    assert orient.to_physical(6, 180) == 6       # middle key fixed
    assert orient.to_physical(13, 180) == 13     # status: firmware element, fixed
    assert orient.to_physical(15, 180) == 16     # aux L <-> aux R
    assert orient.to_physical(17, 180) == 19     # encoders reverse
    assert orient.to_physical(18, 180) == 18
    assert orient.icon_degrees(180) == 180


def test_rotate_png_180_keeps_size_and_changes_bytes():
    src = layout.render_icon({"fg": "#ffffff"}, text="A")
    out = orient.rotate_png(src, 180)
    assert out != src
    with Image.open(io.BytesIO(src)) as a, Image.open(io.BytesIO(out)) as b:
        assert a.size == b.size
    assert orient.rotate_png(src, 0) is src


def _icon_cells(payload):
    z = zipfile.ZipFile(io.BytesIO(payload))
    man = json.loads(z.read("manifest.json"))
    return {c: v["ViewParam"][0]["Icon"] for c, v in man.items()
            if v["ViewParam"][0].get("Icon")}


def test_layout_places_logical_icons_at_physical_cells():
    pg = config.Page(keys={0: {"gamepad": 1, "label": "AAA"},
                           12: {"gamepad": 13, "label": "ZZZ"}})

    at0 = _icon_cells(layout.build_set_buttons(pg, {}, 0))
    at180 = _icon_cells(layout.build_set_buttons(pg, {}, 180))

    # key 0 sits at cell 0_0 normally, at 2_2 (physical key 12's slot) upside down
    assert at0["0_0"] and at0["2_2"]
    assert at180["0_0"] and at180["2_2"]
    assert at0["0_0"] != at180["0_0"]            # different key + rotated -> different icon
