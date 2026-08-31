"""Read a game's own control bindings and match them to the virtual gamepad,
so the deck can show what each button does in-game without digging through
config files.

Currently supports Le Mans Ultimate (`UserData/player/direct input.json`).
rF2/LMU numbers inputs in one namespace: axis half-ids fill 0-31, buttons
start at 32. Our uinput pad has 0 axes, so game id N == our gamepad button
(N - 32 + 1), 1-based.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

LMU_BUTTON_ID_BASE = 32
_GAMEPAD_HINT = "d200x button box"  # match our device by name prefix

_STEAM_ROOTS = [
    Path.home() / ".steam/steam/steamapps",
    Path.home() / ".local/share/Steam/steamapps",
    Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam/steamapps",
]
_LMU_SUBDIR = "common/Le Mans Ultimate"


def _steam_libraries() -> list[Path]:
    libs: list[Path] = []
    for root in _STEAM_ROOTS:
        if root.is_dir():
            libs.append(root)
        vdf = root / "libraryfolders.vdf"
        if vdf.is_file():
            for m in re.finditer(r'"path"\s*"([^"]+)"', vdf.read_text(errors="replace")):
                libs.append(Path(m.group(1)) / "steamapps")
    return libs


def find_lmu() -> str | None:
    for lib in _steam_libraries():
        p = lib / _LMU_SUBDIR
        if (p / "UserData/player/direct input.json").is_file():
            return str(p)
    return None


def import_lmu(install_path: str | Path) -> dict[int, list[str]]:
    """{gamepad button (1-based) -> [in-game control names]} for our device."""
    f = Path(install_path) / "UserData" / "player" / "direct input.json"
    if not f.is_file():
        raise FileNotFoundError(f"{f} not found -- is this the Le Mans Ultimate folder?")
    data = json.loads(f.read_text())
    ours = [n for n in data.get("Devices", {}) if _GAMEPAD_HINT in n.lower()]
    result: dict[int, list[str]] = {}
    for section in ("Input", "Alternative Input"):
        for control, b in (data.get(section) or {}).items():
            if not isinstance(b, dict) or b.get("device") not in ours:
                continue
            btn = int(b["id"]) - LMU_BUTTON_ID_BASE + 1
            if btn >= 1:
                result.setdefault(btn, [])
                if control not in result[btn]:
                    result[btn].append(control)
    return result


_IMPORTERS = {"lmu": import_lmu}
_FINDERS = {"lmu": find_lmu}


def available_games() -> dict[str, dict]:
    out = {}
    for game, finder in _FINDERS.items():
        out[game] = {"path": finder()}
    return out


def import_game(game: str, install_path: str | Path) -> dict[int, list[str]]:
    fn = _IMPORTERS.get(game)
    if fn is None:
        raise ValueError(f"no importer for game {game!r}")
    return fn(install_path)


def apply_labels(profile, button_names: dict[int, list[str]], overwrite: bool = True) -> dict:
    """Set labels from an import map (LCD keys + knob sub-bindings, the latter
    shown only in the editor). Returns a report of what changed."""
    applied: dict[int, str] = {}
    skipped: dict[int, str] = {}
    seen: set[int] = set()

    def annotate(b: dict) -> None:
        n = b.get("gamepad")
        if not isinstance(n, int):
            return
        seen.add(n)
        names = button_names.get(n)
        if not names:
            return
        label = " / ".join(names)
        if b.get("label") and not overwrite:
            skipped[n] = label
        else:
            b["label"] = label
            applied[n] = label

    for page in profile.pages:
        for b in page.keys.values():
            annotate(b)
        for knob in page.knobs.values():
            for sub in knob.values():
                if isinstance(sub, dict):
                    annotate(sub)

    unmatched = {n: " / ".join(v) for n, v in button_names.items() if n not in seen}
    return {"applied": applied, "skipped": skipped, "unmatched": unmatched}
