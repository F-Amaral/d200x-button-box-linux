"""Parametric icon composition -- a base tell-tale + drawn overlays.

Precedence (lowest to highest):

* **`COMPOSED`** (this file) -- the shipped defaults, as parametric dicts.
* **`assets/composed.yaml`** -- maintainer tweaks made in the editor and
  promoted with `d200x-button-box icons promote` (`promote_spec()`); committed,
  merged over `COMPOSED` at import.
* **`~/.config/d200x-button-box/icons.yaml`** -- a user's own edits from the
  web editor (`user_specs()` / `save_user_spec()`), rendered to
  `config.user_icons_dir()/<name>.png` which the icon resolver prefers.

`tools/build-composed-icons.py` renders the resolved `COMPOSED` (defaults +
`composed.yaml`) to the committed PNGs in `assets/telltales/`.

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
Any layer may add `"color": "#4a9eff"` to draw itself in a fixed colour instead
of following the key's icon colour (e.g. tint one arrow of `turn` blue).
"""

from __future__ import annotations

import io
import math

_DIRS = {"right": 0.0, "down": 90.0, "left": 180.0, "up": 270.0}


def names() -> tuple[str, ...]:
    """Built-in composed-icon names (the ones with a shipped PNG)."""
    return tuple(COMPOSED)


def has(name: str) -> bool:
    return name in COMPOSED


# --- user specs (editor) ------------------------------------------------
def _user_yaml():
    from .config import CONFIG_DIR

    return CONFIG_DIR / "icons.yaml"


def user_specs() -> dict[str, dict]:
    try:
        import yaml

        p = _user_yaml()
        if p.is_file():
            return {k: v for k, v in (yaml.safe_load(p.read_text()) or {}).items()
                    if isinstance(v, dict)}
    except Exception:  # noqa: BLE001
        pass
    return {}


def effective_spec(name: str) -> dict | None:
    """A copy of the spec that would render `name`: user override, else built-in."""
    import copy

    u = user_specs()
    s = u[name] if name in u else COMPOSED.get(name)
    return copy.deepcopy(s) if s is not None else None


def all_specs() -> dict[str, dict]:
    """{name: {spec, builtin, customised}} for every composed icon we know."""
    import copy

    u = user_specs()
    out: dict[str, dict] = {}
    for n, s in COMPOSED.items():
        out[n] = {"spec": copy.deepcopy(u.get(n, s)), "builtin": True, "customised": n in u}
    for n, s in u.items():
        if n not in out:
            out[n] = {"spec": copy.deepcopy(s), "builtin": False, "customised": True}
    return out


def save_user_spec(name: str, spec: dict | None) -> None:
    """Set (spec) or clear (None) a user override, then re-render the PNGs."""
    import yaml

    p = _user_yaml()
    data = {}
    if p.is_file():
        data = yaml.safe_load(p.read_text()) or {}
    if spec is None:
        data.pop(name, None)
    else:
        data[name] = spec
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    render_user_icons()


def render_user_icons(*, only_missing: bool = False) -> int:
    """Render user specs to ``config.user_icons_dir()/<name>.png``.

    ``only_missing`` (daemon startup): render just the specs whose PNG is
    absent or older than ``icons.yaml``, and never delete -- so a hand-tweaked
    ``generated/`` PNG survives a restart. The default (called after an editor
    save) rewrites everything and prunes overrides that were removed.
    """
    from .config import user_icons_dir

    out = user_icons_dir()
    specs = user_specs()
    if not specs and not out.is_dir():
        return 0
    out.mkdir(parents=True, exist_ok=True)
    ym = _user_yaml().stat().st_mtime if _user_yaml().is_file() else 0.0
    for name, spec in specs.items():
        png = out / f"{_safe(name)}.png"
        if only_missing and png.is_file() and png.stat().st_mtime >= ym:
            continue
        png.write_bytes(render(spec, "#ffffff", 256))
    if not only_missing:
        keep = {f"{_safe(n)}.png" for n in specs}
        for f in out.glob("*.png"):
            if f.name not in keep:
                f.unlink()
    return len(specs)


def _bundled_yaml():
    """Maintainer-committed spec overrides, merged over the ``COMPOSED`` code dict."""
    from pathlib import Path

    return Path(__file__).parent / "assets" / "composed.yaml"


def promote_spec(name: str) -> "Path":
    """Maintainer action: bake a tuned icon into the shipped defaults.

    Renders the current effective spec (a user override if present, else the
    built-in) to the committed ``assets/telltales/<name>.png``, records it in
    ``assets/composed.yaml``, and clears the ``icons.yaml`` override. Needs a
    writable package dir -- run from a source checkout / editable install.
    """
    import yaml

    spec = effective_spec(name)
    if spec is None:
        raise KeyError(name)
    png = _bundled_yaml().parent / "telltales" / f"{_safe(name)}.png"
    png.write_bytes(render(spec, "#ffffff", 256))
    p = _bundled_yaml()
    data = (yaml.safe_load(p.read_text()) if p.is_file() else {}) or {}
    data[name] = spec
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    COMPOSED[name] = spec
    save_user_spec(name, None)  # drop the override -- it's the default now
    return png


def _safe(name: str) -> str:
    keep = "".join(c for c in (name or "") if c.isalnum() or c in "-_")
    return keep or "icon"


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


def _region(img, S, ly, fg):
    """Recolour / fill part of the composited image, clipped to a rect or
    ellipse.  `fill` floods the symbol's *enclosed* interior (grown a couple of
    pixels so it meets the outline with no gap), keeping the original outline;
    `color` then repaints the outline in that colour, preserving its edges."""
    from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter

    cx, cy = ly.get("at", [0.5, 0.5])
    w, h = ly.get("size", [0.5, 1.0])
    x0, y0 = max(0, round((cx - w / 2) * S)), max(0, round((cy - h / 2) * S))
    x1, y1 = min(S, round((cx + w / 2) * S)), min(S, round((cy + h / 2) * S))
    if x1 <= x0 or y1 <= y0:
        return
    rw, rh = x1 - x0, y1 - y0

    shape = Image.new("L", (rw, rh), 0)
    sd = ImageDraw.Draw(shape)
    (sd.ellipse if ly.get("shape") == "ellipse" else sd.rectangle)([0, 0, rw - 1, rh - 1], fill=255)

    crop = img.crop((x0, y0, x1, y1))
    a = crop.getchannel("A")
    out = crop.convert("RGBA")

    if ly.get("fill"):
        OUT = 128
        reach = a.point(lambda v: 255 if v <= 24 else 0)         # clearly transparent
        for c in ((0, 0), (rw - 1, 0), (0, rh - 1), (rw - 1, rh - 1)):
            if reach.getpixel(c) == 255:
                ImageDraw.floodfill(reach, c, OUT)               # flood in from the edge
        hollow = reach.point(lambda v: 255 if v == 255 else 0)   # only the enclosed transparent
        hollow = hollow.filter(ImageFilter.MaxFilter(5))         # grow under the outline's inner edge
        m = ImageChops.multiply(hollow, shape)
        out = Image.composite(Image.new("RGBA", (rw, rh), ImageColor.getrgb(ly["fill"]) + (255,)), out, m)

    if ly.get("color"):
        tint = Image.new("RGBA", (rw, rh), ImageColor.getrgb(ly["color"]) + (0,))
        tint.putalpha(ImageChops.multiply(a, shape))             # keep the outline's own edges/AA
        out.alpha_composite(tint)

    img.paste(out, (x0, y0))


def render(spec: dict | str, colour: str, size: int = 256) -> bytes:
    """Render a spec (or a built-in name) to an RGBA PNG.

    `base_scale` is the base's longest side as a fraction of the canvas, so a
    wide symbol like the seat fills the frame at scale 1.0 -- matching the
    fetched tell-tales, which are trimmed to a square and scaled to fill.
    """
    from PIL import ImageColor

    from . import telltales

    Image, ImageDraw = _pil()
    if isinstance(spec, str):
        spec = COMPOSED[spec]
    S = size
    fg = ImageColor.getrgb(colour or "#ffffff") + (255,)
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
        # a layer can force its own colour (e.g. tint one arrow to mark left/right);
        # otherwise it follows the key's icon colour like the base
        lc = (ImageColor.getrgb(ly["color"]) + (255,)) if ly.get("color") else fg
        if t == "arrow":
            _arrow(d, S, ly["at"], _angle(ly.get("dir", 0)),
                   ly.get("len", 0.3), ly.get("head", 0.12), ly.get("w", 0.05), lc)
        elif t == "arc":
            _arc(d, S, ly["at"], ly["r"], ly.get("deg", [0, 360]),
                 ly.get("w", 0.05), lc, ly.get("arrow"),
                 head=(ly["head"] * S if "head" in ly else None))
        elif t == "line":
            _line(d, S, ly["from"], ly["to"], ly.get("w", 0.05), lc)
        elif t == "tick":
            _tick(d, S, ly["at"], _angle(ly.get("dir", 90)), ly.get("len", 0.05), ly.get("w", 0.04), lc)
        elif t == "region":
            _region(img, S, ly, fg)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _or_full(im):
    return im.getbbox() or (0, 0, im.size[0], im.size[1])


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


def _merge_bundled_overrides() -> None:
    """Apply maintainer tweaks from ``assets/composed.yaml`` (via `promote_spec`)."""
    p = _bundled_yaml()
    if not p.is_file():
        return
    try:
        import yaml

        for k, v in (yaml.safe_load(p.read_text()) or {}).items():
            if isinstance(v, dict):
                COMPOSED[k] = v
    except Exception:  # noqa: BLE001
        pass


_merge_bundled_overrides()
