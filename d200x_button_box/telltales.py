"""Real automotive tell-tale symbols (mostly ISO 7000, all public domain).

Bundled as white-on-transparent PNGs in ``assets/telltales/``; `tint()`
recolours one to any style colour at render time (pure Pillow, no SVG
dependency). Provenance: ``assets/telltales/CREDITS.md``.

A user-generated PNG in ``config.user_icons_dir()`` (rendered from an
``icons.yaml`` spec by the icon editor) shadows a bundled one of the same name.
"""

from __future__ import annotations

import functools
import io
from pathlib import Path

_DIR = Path(__file__).parent / "assets" / "telltales"


def _user_dir() -> Path:
    from .config import user_icons_dir

    return user_icons_dir()


def _path(name: str) -> Path | None:
    u = _user_dir() / f"{name}.png"
    if u.is_file():
        return u
    b = _DIR / f"{name}.png"
    return b if b.is_file() else None


@functools.lru_cache(maxsize=1)
def _bundled() -> frozenset[str]:
    return frozenset(p.stem for p in _DIR.glob("*.png"))


def names() -> list[str]:
    extra = {p.stem for p in _user_dir().glob("*.png")} if _user_dir().is_dir() else set()
    return sorted(_bundled() | extra)


def has(name: str) -> bool:
    return _path(name or "") is not None


def _silhouette(name: str):
    from PIL import Image

    return Image.open(_path(name)).convert("RGBA")


def _has_colour(im) -> bool:
    """True if the PNG has saturated (non-greyscale) opaque pixels -- a
    hand-coloured composed icon, whose colours must survive `tint()`."""
    small = im.resize((16, 16))
    px = small.load()
    for y in range(16):
        for x in range(16):
            r, g, b, a = px[x, y]
            if a > 20 and max(r, g, b) - min(r, g, b) > 40:
                return True
    return False


def tint(name: str, colour: str, size: int) -> bytes:
    """A `size`x`size` RGBA PNG of tell-tale `name` filled with `colour`.

    A plain white/grey symbol is recoloured wholesale. A composed icon that
    carries its own colours keeps them -- only its greyscale parts take
    `colour`.
    """
    from PIL import Image, ImageColor, ImageOps

    sil = _silhouette(name)
    fg = ImageColor.getrgb(colour or "#ffffff")
    if _has_colour(sil):
        px = sil.load()
        solid = Image.new("RGBA", sil.size, (0, 0, 0, 0))
        op = solid.load()
        for y in range(sil.height):
            for x in range(sil.width):
                r, g, b, a = px[x, y]
                if a == 0:
                    continue
                op[x, y] = (r, g, b, a) if max(r, g, b) - min(r, g, b) > 40 else fg + (a,)
    else:
        solid = Image.new("RGBA", sil.size, fg + (255,))
        solid.putalpha(sil.getchannel("A"))
    if solid.size != (size, size):
        solid = ImageOps.contain(solid, (size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(solid, ((size - solid.size[0]) // 2, (size - solid.size[1]) // 2), solid)
        solid = canvas
    buf = io.BytesIO()
    solid.save(buf, format="PNG")
    return buf.getvalue()
