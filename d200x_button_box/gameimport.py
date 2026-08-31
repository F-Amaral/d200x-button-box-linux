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
    data = json.loads(_lmu_config_path(install_path).read_text())
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


# --------------------------------------------------------------------------- #
#  Writing the game's config (bind-to-game)
# --------------------------------------------------------------------------- #
def _lmu_config_path(install: str | Path) -> Path:
    f = Path(install) / "UserData" / "player" / "direct input.json"
    if not f.is_file():
        raise FileNotFoundError(f"{f} not found -- is this the Le Mans Ultimate folder?")
    return f


def _lmu_device_key(data: dict) -> str | None:
    for name in data.get("Devices", {}):
        if _GAMEPAD_HINT in name.lower():
            return name
    return None


def lmu_controls(install: str | Path) -> dict:
    """Every bindable control name + whether our device is in the file yet."""
    data = json.loads(_lmu_config_path(install).read_text())
    names = sorted(set(data.get("Input", {})) | set(data.get("Alternative Input", {})))
    key = _lmu_device_key(data)
    bound = {}
    if key:
        for section in ("Alternative Input", "Input"):  # Input wins if both
            for control, b in (data.get(section) or {}).items():
                if isinstance(b, dict) and b.get("device") == key:
                    bound[control] = int(b["id"]) - LMU_BUTTON_ID_BASE + 1
    return {"controls": names, "device_present": key is not None, "bound": bound}


def lmu_bind(install: str | Path, control: str, button: int | None) -> dict:
    """Point `control` at our gamepad `button` (1-based), or clear it (button=None).

    Only touches the `Input` section. The game must be closed — it reads this
    file at startup. A one-time backup is written next to the file.
    """
    path = _lmu_config_path(install)
    data = json.loads(path.read_text())
    key = _lmu_device_key(data)
    if key is None:
        raise ValueError(
            "the D200x Button Box is not in the game's config yet -- bind any "
            "one control to it in-game once so the game records the device, "
            "then this will work"
        )
    if control not in data.get("Input", {}) and control not in data.get("Alternative Input", {}):
        raise ValueError(f"unknown control {control!r}")

    backup = path.with_suffix(path.suffix + ".d200x-bak")
    if not backup.exists():
        backup.write_text(path.read_text())

    section = data.setdefault("Input", {})
    if button is None:
        section.pop(control, None)
    else:
        section[control] = {"device": key, "id": int(button) + LMU_BUTTON_ID_BASE - 1}

    path.write_text(json.dumps(data, indent=1))
    return {"ok": True, "control": control, "button": button, "backup": str(backup)}


_IMPORTERS = {"lmu": import_lmu}
_FINDERS = {"lmu": find_lmu}
_CONTROL_LISTERS = {"lmu": lmu_controls}
_BINDERS = {"lmu": lmu_bind}


def available_games() -> dict[str, dict]:
    out = {}
    for game, finder in _FINDERS.items():
        out[game] = {"path": finder(), "can_write": game in _BINDERS}
    return out


def import_game(game: str, install_path: str | Path) -> dict[int, list[str]]:
    fn = _IMPORTERS.get(game)
    if fn is None:
        raise ValueError(f"no importer for game {game!r}")
    return fn(install_path)


def game_controls(game: str, install_path: str | Path) -> dict:
    fn = _CONTROL_LISTERS.get(game)
    if fn is None:
        raise ValueError(f"cannot list controls for {game!r}")
    return fn(install_path)


def game_bind(game: str, install_path: str | Path, control: str, button: int | None) -> dict:
    fn = _BINDERS.get(game)
    if fn is None:
        raise ValueError(f"cannot write bindings for {game!r}")
    return fn(install_path, control, button)


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
