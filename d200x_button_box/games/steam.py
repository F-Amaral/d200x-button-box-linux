"""Steam library discovery, shared by the game modules."""

from __future__ import annotations

import re
from pathlib import Path

_ROOTS = [
    Path.home() / ".steam/steam/steamapps",
    Path.home() / ".local/share/Steam/steamapps",
    Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam/steamapps",
]


def libraries() -> list[Path]:
    """Every `steamapps` dir on this machine (default roots + libraryfolders.vdf)."""
    libs: list[Path] = []
    for root in _ROOTS:
        if root.is_dir():
            libs.append(root)
        vdf = root / "libraryfolders.vdf"
        if vdf.is_file():
            for m in re.finditer(r'"path"\s*"([^"]+)"', vdf.read_text(errors="replace")):
                libs.append(Path(m.group(1)) / "steamapps")
    return libs
