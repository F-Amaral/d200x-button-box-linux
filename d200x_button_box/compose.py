"""Parametric icon composition -- a base tell-tale + drawn overlays.

This is a **generator**: `tools/build-composed-icons.py` renders each spec in
`COMPOSED` to a committed PNG in `assets/telltales/`. It's the path for any
future "combine two symbols / add an arrow" icon -- edit a spec (data, not
code), re-run the tool, commit the PNG.

A spec is a plain dict. All coordinates and sizes are fractions of the output
square (0..1):

    spec = {
      "base": "seat",            # a telltale name (optional)
      "base_scale": 0.58,        # base width as a fraction of the canvas
      "base_at": [0.44, 0.46],   # base centre
      "layers": [
        {"type": "line",  "from": [0.08, 0.9], "to": [0.8, 0.9], "w": 0.045},
        {"type": "arrow", "at": [0.5, 0.68], "dir": "left", "len": 0.34, "head": 0.12, "w": 0.05},
        {"type": "arc",   "at": [0.5, 0.55], "r": 0.16, "deg": [175, 390], "arrow": "end", "w": 0.034},
        {"type": "tick",  "at": [0.36, 0.55], "dir": "down", "len": 0.05, "w": 0.034},
      ],
    }

`dir` is "up"/"down"/"left"/"right" or a number of degrees (0 = right, clockwise).
"""

from __future__ import annotations

import io
import math

_DIRS = {"right": 0.0, "down": 90.0, "left": 180.0, "up": 270.0}


def names() -> tuple[str, ...]:
    return tuple(COMPOSED)


def has(name: str) -> bool:
    return name in COMPOSED


def _pil():
    from PIL import Image, ImageDraw

    return Image, ImageDraw


def _angle(d) -> float:
    if isinstance(d, (int, float)):
        return math.radians(float(d))
    return math.radians(_DIRS.get(str(d).lower(), 0.0))


def _arrow(draw, S, at, ang, length, head, w, fg):
    x, y = at[0] * S, at[1] * S
    L, H, W = length * S, head * S, max(2, round(w * S))
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    nx, ny = x + ux * (L - H), y + uy * (L - H)
    tx, ty = x + ux * L, y + uy * L
    draw.line([x, y, nx, ny], fill=fg, width=W)
    draw.polygon([
        (tx, ty),
        (nx + px * H * 0.58, ny + py * H * 0.58),
        (nx - px * H * 0.58, ny - py * H * 0.58),
    ], fill=fg)


def _arc(draw, S, at, r, deg, w, fg, arrow, head=None):
    cx, cy, R = at[0] * S, at[1] * S, r * S
    W = max(2, round(w * S))
    a0, a1 = deg
    draw.arc([cx - R, cy - R, cx + R, cy + R], a0, a1, fill=fg, width=W)
    if arrow in ("end", "start"):
        a = math.radians(a1 if arrow == "end" else a0)
        ex, ey = cx + R * math.cos(a), cy + R * math.sin(a)
        tang = a + (math.pi / 2 if arrow == "end" else -math.pi / 2)
        ux, uy = math.cos(tang), math.sin(tang)
        px, py = -uy, ux
        # a solid triangle head sized to the arc, not the stroke
        hh = (head if head is not None else min(R * 0.5, 0.085 * S))
        draw.polygon([
            (ex + ux * hh, ey + uy * hh),
            (ex - ux * hh * 0.35 + px * hh * 0.62, ey - uy * hh * 0.35 + py * hh * 0.62),
            (ex - ux * hh * 0.35 - px * hh * 0.62, ey - uy * hh * 0.35 - py * hh * 0.62),
        ], fill=fg)


def _line(draw, S, p0, p1, w, fg):
    draw.line([p0[0] * S, p0[1] * S, p1[0] * S, p1[1] * S], fill=fg, width=max(2, round(w * S)))


def _tick(draw, S, at, ang, length, w, fg):
    x, y = at[0] * S, at[1] * S
    ux, uy = math.cos(ang), math.sin(ang)
    draw.line([x, y, x + ux * length * S, y + uy * length * S], fill=fg, width=max(2, round(w * S)))


def render(spec: dict | str, colour: str, size: int = 256) -> bytes:
    """Render a spec (or a built-in name) to an RGBA PNG.

    `base_scale` is the base's longest side as a fraction of the canvas, so a
    wide symbol like the seat fills the frame at scale 1.0 -- matching the
    fetched tell-tales, which are trimmed to a square and scaled to fill.
    """
    from . import telltales

    Image, ImageDraw = _pil()
    if isinstance(spec, str):
        spec = COMPOSED[spec]
    S = size
    fg = _rgba(colour)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    base = spec.get("base")
    if base and telltales.has(base):
        # tint() returns a target-sized square with the symbol contained + centred
        target = max(1, round(spec.get("base_scale", 0.6) * S))
        with Image.open(io.BytesIO(telltales.tint(base, colour, target))) as sq:
            sq = sq.convert("RGBA").crop(_or_full(sq.convert("RGBA")))
            bx, by = spec.get("base_at", [0.5, 0.5])
            img.alpha_composite(sq, (round(bx * S - sq.size[0] / 2), round(by * S - sq.size[1] / 2)))

    d = ImageDraw.Draw(img)
    for ly in spec.get("layers", []):
        t = ly.get("type")
        if t == "arrow":
            _arrow(d, S, ly["at"], _angle(ly.get("dir", 0)),
                   ly.get("len", 0.3), ly.get("head", 0.12), ly.get("w", 0.05), fg)
        elif t == "arc":
            _arc(d, S, ly["at"], ly["r"], ly.get("deg", [0, 360]),
                 ly.get("w", 0.05), fg, ly.get("arrow"),
                 head=(ly["head"] * S if "head" in ly else None))
        elif t == "line":
            _line(d, S, ly["from"], ly["to"], ly.get("w", 0.05), fg)
        elif t == "tick":
            _tick(d, S, ly["at"], _angle(ly.get("dir", 90)), ly.get("len", 0.05), ly.get("w", 0.04), fg)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _or_full(im):
    return im.getbbox() or (0, 0, im.size[0], im.size[1])


def _rgba(colour: str):
    c = (colour or "#ffffff").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255


# --------------------------------------------------------------------------- #
#  Built-in composed icons -- edit, then run tools/build-composed-icons.py
# --------------------------------------------------------------------------- #
# Seat PNG at scale 1.0 fills the frame; the cushion (sit surface, inside the
# "seat" opening) is centred around x~0.35, y~0.60. Engine at ~0.95: the round
# body's interior is centred at x~0.50, y~0.62.
_SEAT_FULL = {"base": "seat", "base_scale": 1.0, "base_at": [0.5, 0.5]}
_SEAT_ROOM = {"base": "seat", "base_scale": 0.86, "base_at": [0.42, 0.46]}  # up/down need room


def _seat_v(direction):  # up / down -- vertical arrow beside the seat, floor line
    y_near, y_far = 0.34, 0.78
    at = [0.90, y_far] if direction == "up" else [0.90, y_near]
    return {
        **_SEAT_ROOM,
        "layers": [
            {"type": "line", "from": [0.06, 0.92], "to": [0.78, 0.92], "w": 0.042},
            {"type": "arrow", "at": at, "dir": direction, "len": y_far - y_near,
             "head": 0.15, "w": 0.052},
        ],
    }


def _seat_h(direction):  # fore / aft -- one arrow in the hollow of the seat base
    # cushion top is ~y0.60, base bottom ~y0.80; the empty middle is ~y0.70
    at = [0.54, 0.70] if direction == "left" else [0.13, 0.70]
    return {
        **_SEAT_FULL,
        "layers": [
            {"type": "arrow", "at": at, "dir": direction, "len": 0.41, "head": 0.14, "w": 0.05},
        ],
    }


COMPOSED: dict[str, dict] = {
    "engine_start": {
        "base": "engine", "base_scale": 0.95, "base_at": [0.5, 0.5],
        "layers": [
            {"type": "arc", "at": [0.5, 0.62], "r": 0.185, "deg": [175, 175 + 182],
             "arrow": "end", "w": 0.032, "head": 0.075},
            {"type": "tick", "at": [0.315, 0.62], "dir": "up", "len": 0.065, "w": 0.032},
        ],
    },
    "seat_fore": _seat_h("left"),
    "seat_aft": _seat_h("right"),
    "seat_up": _seat_v("up"),
    "seat_down": _seat_v("down"),
    "seat_recline": {
        **_SEAT_FULL,
        "layers": [
            {"type": "arc", "at": [0.66, 0.22], "r": 0.16, "deg": [205, 205 + 150],
             "arrow": "end", "w": 0.048, "head": 0.072},
        ],
    },
}
