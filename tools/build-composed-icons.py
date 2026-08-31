#!/usr/bin/env python3
"""Render every spec in `d200x_button_box.compose.COMPOSED` to a committed
white-on-transparent PNG in `assets/telltales/`.

Composed icons are a base ISO tell-tale + drawn arrows / arcs / lines, for
symbols that don't exist as a single public-domain source (engine start, the
seat-adjust family -- ISO 7000-1387/1428/1706/1707, none on Wikimedia Commons).

Edit the specs in `compose.py`, run this, commit the PNGs.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / "d200x_button_box" / "assets" / "telltales"


def main() -> int:
    from PIL import Image

    from d200x_button_box import compose

    for name in compose.names():
        png = compose.render(name, "#ffffff", size=256)
        with Image.open(io.BytesIO(png)) as im:
            im.convert("RGBA").save(DEST / f"{name}.png")
        print(f"  {name}.png")
    print(f"{len(compose.names())} composed icons -> {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
