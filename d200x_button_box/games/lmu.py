"""Le Mans Ultimate -- controls in `UserData/player/direct input.json` (JSON).

rF2/LMU number every input in one namespace: axis half-ids fill 0-31, buttons
start at 32. Our uinput pad has 0 axes, so game id N == our gamepad button
(N - 32 + 1), 1-based.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import Game
from .steam import libraries

_BUTTON_ID_BASE = 32
_DECK = "d200x button box"  # our virtual pad, matched by device name


def find() -> str | None:
    for lib in libraries():
        p = lib / "common" / "Le Mans Ultimate"
        if (p / "UserData/player/direct input.json").is_file():
            return str(p)
    return None


def _config(install: str | Path) -> Path:
    f = Path(install) / "UserData" / "player" / "direct input.json"
    if not f.is_file():
        raise FileNotFoundError(f"{f} not found -- is this the Le Mans Ultimate folder?")
    return f


def _device_key(data: dict) -> str | None:
    for name in data.get("Devices", {}):
        if _DECK in name.lower():
            return name
    return None


def read(install: str | Path) -> dict[int, list[str]]:
    """{gamepad button (1-based) -> [in-game control names]} for our device."""
    data = json.loads(_config(install).read_text())
    ours = [n for n in data.get("Devices", {}) if _DECK in n.lower()]
    result: dict[int, list[str]] = {}
    for section in ("Input", "Alternative Input"):
        for control, b in (data.get(section) or {}).items():
            if not isinstance(b, dict) or b.get("device") not in ours:
                continue
            btn = int(b["id"]) - _BUTTON_ID_BASE + 1
            if btn >= 1:
                result.setdefault(btn, [])
                if control not in result[btn]:
                    result[btn].append(control)
    return result


def controls(install: str | Path) -> dict:
    """Every bindable control name + whether our device is in the file yet."""
    data = json.loads(_config(install).read_text())
    names = sorted(set(data.get("Input", {})) | set(data.get("Alternative Input", {})))
    key = _device_key(data)
    bound = {}
    if key:
        for section in ("Alternative Input", "Input"):  # Input wins if both
            for control, b in (data.get(section) or {}).items():
                if isinstance(b, dict) and b.get("device") == key:
                    bound[control] = int(b["id"]) - _BUTTON_ID_BASE + 1
    return {"controls": names, "device_present": key is not None, "bound": bound}


def write(install: str | Path, control: str, button: int | None) -> dict:
    """Point `control` at our gamepad `button` (1-based), or clear it (button=None).

    Only touches the `Input` section. The game must be closed -- it reads this
    file at startup. A one-time backup is written next to the file.
    """
    path = _config(install)
    data = json.loads(path.read_text())
    key = _device_key(data)
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
        section[control] = {"device": key, "id": int(button) + _BUTTON_ID_BASE - 1}

    path.write_text(json.dumps(data, indent=1))
    return {"ok": True, "control": control, "button": button, "backup": str(backup)}


GAME = Game(
    key="lmu", label="LMU", detect=("Le Mans Ultimate", "LeMansUltimate"),
    find=find, read=read, controls=controls, write=write,
)
