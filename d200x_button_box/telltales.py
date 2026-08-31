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


def tint(name: str, colour: str, size: int) -> bytes:
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
