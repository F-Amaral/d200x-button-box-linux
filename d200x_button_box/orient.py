"""Physical rotation of the deck.

Mount the D200x at 0 or 180 degrees. Everything outside this module -- the
config, the API, the web UI, in-game bindings -- works in *logical* (as-mounted)
coordinates: logical key 0 is always the top-left key as you see it. This module
is the only place that maps logical <-> physical hardware indices and rotates the
rendered icons.

180 (upside down): the 13 LCD keys reverse (logical i <-> physical 12 - i), the
two aux buttons swap, the three encoders reverse order, and every icon is turned
180. Encoder turn direction is unchanged (an in-plane spin keeps clockwise
clockwise). The wide status strip is a fixed firmware element -- it physically
stays bottom-right, so at 180 it lands at your top-left; its icon is rotated but
the firmware clock/load text can't be (use status mode "off" + a custom icon).

90 / 270 aren't supported: the wide status strip can't rotate onto a portrait
grid.
"""

from __future__ import annotations

import io

VALID = (0, 180)
_STATUS = 13


def _map(rotation: int) -> dict[int, int]:
    """logical <-> physical index. An involution, so the same map converts both
    ways."""
    if rotation == 180:
        m = {i: 12 - i for i in range(13)}   # LCD keys reverse
        m[_STATUS] = _STATUS                 # firmware element, fixed slot
        m[15], m[16] = 16, 15               # aux L <-> aux R
        m[17], m[19] = 19, 17              # encoders reverse; the middle one stays
        return m
    return {}


def to_physical(logical: int, rotation: int) -> int:
    return _map(rotation).get(logical, logical)


def to_logical(physical: int, rotation: int) -> int:
    return _map(rotation).get(physical, physical)


def icon_degrees(rotation: int) -> int:
    """How far to turn each rendered icon so it reads upright once mounted."""
    return rotation % 360


def rotate_png(png: bytes | None, degrees: int) -> bytes | None:
    if not png or degrees % 360 == 0:
        return png
    from PIL import Image

    with Image.open(io.BytesIO(png)) as im:
        out = im.convert("RGBA").rotate(-degrees % 360, expand=False)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
