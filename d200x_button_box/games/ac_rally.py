"""Assetto Corsa Rally (Unreal Engine 5) -- player rebindings live in a GVAS
SaveGame, `EnhancedInputUserSettings.sav`. Read-only for now.

Each mapping is a run of four length-prefixed FStrings:
    <ActionName> <HardwareKey> "RawInput" "SteeringWheel"
HardwareKey is "GenericUSBController_Button<N>_<VID>_<PID>" (or "None"). Our
virtual pad (gamepad.py: vendor=0x1209 product=0xD200) shows up as
"..._Button<N>_1209_D200", and button N maps 1:1 to our gamepad button N.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from . import Game
from .steam import libraries

_APPIDS = ("3917090", "3919070")
_SAV_REL = (
    "pfx/drive_c/users/steamuser/AppData/Local/acr/Saved/SaveGames/"
    "EnhancedInputUserSettings.sav"
)
_DECK_RE = re.compile(r"GenericUSBController_Button(\d+)_1209_D200$", re.I)


def find() -> str | None:
    for lib in libraries():
        for appid in _APPIDS:
            sav = lib / "compatdata" / appid / _SAV_REL
            if sav.is_file():
                return str(sav)
    return None


def _sav(path: str | Path) -> Path:
    """Accept the .sav itself, a compatdata/<appid> dir, or a Steam library root."""
    p = Path(path)
    if p.is_file():
        return p
    for c in [p / _SAV_REL, *(p / "compatdata" / a / _SAV_REL for a in _APPIDS)]:
        if c.is_file():
            return c
    raise FileNotFoundError(f"EnhancedInputUserSettings.sav not found under {path}")


def _fstrings(data: bytes) -> list[str]:
    """Every length-prefixed ASCII FString in the blob, in order."""
    out: list[str] = []
    i, n = 0, len(data)
    while i < n - 4:
        length = struct.unpack_from("<i", data, i)[0]
        end = i + 4 + length
        if 2 <= length <= 250 and end <= n and data[end - 1] == 0 \
                and all(32 <= b < 127 for b in data[i + 4:end - 1]):
            out.append(data[i + 4:end - 1].decode("latin1"))
            i = end
        else:
            i += 1
    return out


def _mappings(sav: Path) -> list[tuple[str, str]]:
    """[(in-game action, hardware-key string)] for every mapping in the file."""
    s = _fstrings(sav.read_bytes())
    return [
        (s[j], s[j + 1])
        for j in range(len(s) - 3)
        if s[j + 2] == "RawInput" and s[j + 3] == "SteeringWheel"
    ]


def _split_camel(s: str) -> str:
    """'CycleLights' -> 'Cycle Lights' (AC Rally action names are concatenated)."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)


def read(path: str | Path) -> dict[int, list[str]]:
    """{gamepad button (1-based) -> [in-game action names]} bound to our device."""
    result: dict[int, list[str]] = {}
    for action, hwkey in _mappings(_sav(path)):
        m = _DECK_RE.match(hwkey)
        if not m:
            continue
        btn, name = int(m.group(1)), _split_camel(action)
        result.setdefault(btn, [])
        if name not in result[btn]:
            result[btn].append(name)
    return result


GAME = Game(
    key="ac_rally", label="AC Rally",
    detect=("acr.exe", "Assetto Corsa Rally"), find=find, read=read,
)
