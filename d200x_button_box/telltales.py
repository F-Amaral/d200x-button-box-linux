"""Real automotive tell-tale symbols (mostly ISO 7000, all public domain).

Bundled as white-on-transparent PNGs in ``assets/telltales/``; `tint()`
recolours one to any style colour at render time (pure Pillow, no SVG
dependency). Provenance: ``assets/telltales/CREDITS.md``.
"""

from __future__ import annotations

import functools
import io
from pathlib import Path

_DIR = Path(__file__).parent / "assets" / "telltales"


@functools.lru_cache(maxsize=1)
def names() -> tuple[str, ...]:
    return tuple(sorted(p.stem for p in _DIR.glob("*.png")))


def has(name: str) -> bool:
    return (name or "") in names()


@functools.lru_cache(maxsize=64)
def _silhouette(name: str):
    from PIL import Image

    return Image.open(_DIR / f"{name}.png").convert("RGBA").copy()


def tint(name: str, colour: str, size: int) -> "bytes":
    """A `size`x`size` RGBA PNG of tell-tale `name` filled with `colour`."""
    from PIL import Image, ImageOps

    sil = _silhouette(name)
    alpha = sil.getchannel("A")
    solid = Image.new("RGBA", sil.size, _rgb(colour) + (255,))
    solid.putalpha(alpha)
    if solid.size != (size, size):
        solid = ImageOps.contain(solid, (size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(solid, ((size - solid.size[0]) // 2, (size - solid.size[1]) // 2), solid)
        solid = canvas
    buf = io.BytesIO()
    solid.save(buf, format="PNG")
    return buf.getvalue()


def _rgb(colour: str) -> tuple[int, int, int]:
    c = (colour or "#ffffff").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
