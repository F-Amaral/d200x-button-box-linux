#!/usr/bin/env python3
"""(Re)build the tell-tales that come straight from ISO 7000 SVGs on Wikimedia
Commons (public domain). Needs `rsvg-convert`. Run rarely; the PNGs are
committed.

Every *composed* icon (engine_start, seat_*) is a spec in
`d200x_button_box/compose.py` -- rebuild those with `tools/build-composed-icons.py`.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from shutil import which

DEST = Path(__file__).resolve().parent.parent / "d200x_button_box" / "assets" / "telltales"
UA = {"User-Agent": "d200x-buttonbox/1.0 (asset build)"}

# output name -> ISO 7000 reference number
ISO = {
    "ignition": "3033A",         # starter switch (circle + lightning)
    "headlights_auto": "2957",   # automatic low beam (headlamp + "A")
}


def _fetch(ref: str) -> str:
    url = f"https://commons.wikimedia.org/wiki/Special:FilePath/ISO_7000_-_Ref-No_{ref}.svg"
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode()


def _normalise(src: str) -> str:
    """Strip the corner registration marks, force every shape white."""
    src = re.sub(r"<g fill=\"none\".*?</g>\s*", "", src, flags=re.S)
    # 3033A draws its arc as a stroked path with an explicit black stroke
    src = src.replace('fill="none" stroke="#000" stroke-width="10"',
                      'fill="none" stroke="#ffffff" stroke-width="14" stroke-linecap="round"')
    src = re.sub(r'<path d="(m174\.43|m122\.53)', r'<path fill="#ffffff" d="\1', src)
    if "fill=" not in src.split(">", 2)[0]:  # otherwise: white fill on the <svg>
        src = src.replace("<svg ", '<svg fill="#ffffff" ', 1)
    return src


def main() -> int:
    if not which("rsvg-convert"):
        print("need rsvg-convert (librsvg)", file=sys.stderr)
        return 1
    from PIL import Image

    tmp = DEST.parent / "_extra"
    tmp.mkdir(exist_ok=True)

    for name, ref in ISO.items():
        svg = tmp / f"{ref}.svg"
        if not svg.exists():
            svg.write_text(_fetch(ref))
            time.sleep(3)  # Commons rate-limits
        fixed = tmp / f"{ref}.w.svg"
        fixed.write_text(_normalise(svg.read_text()))
        png = tmp / f"{ref}.png"
        subprocess.run(["rsvg-convert", "-w", "512", "-h", "512", "-b", "none", str(fixed), "-o", str(png)], check=True)
        with Image.open(png) as im:
            im = im.convert("RGBA")
            b = im.crop(im.getbbox())
            z = max(b.size)
            cv = Image.new("RGBA", (z, z), (0, 0, 0, 0))
            cv.alpha_composite(b, ((z - b.size[0]) // 2, (z - b.size[1]) // 2))
            m = round(z * 0.05)
            cv = cv.crop((-m, -m, z + m, z + m))
            cv.resize((256, 256), Image.Resampling.LANCZOS).save(DEST / f"{name}.png")
        print(f"  {name}.png  (ISO 7000-{ref})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
