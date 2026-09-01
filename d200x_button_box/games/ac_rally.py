"""Assetto Corsa Rally (Unreal Engine 5) -- player rebindings live in a GVAS
SaveGame, `EnhancedInputUserSettings.sav`.

Each mapping in the active key profile is a run of four length-prefixed FStrings
followed by a constant 6-byte tail:
    <ActionName> <HardwareKey> "RawInput" "SteeringWheel" 05 00 00 00 00 00
HardwareKey is "GenericUSBController_Button<N>_<VID>_<PID>" (or "None"). Our
virtual pad (gamepad.py: vendor=0x1209 product=0xD200) shows up as
"..._Button<N>_1209_D200", and button N maps 1:1 to our gamepad button N.

The mappings are a plain int32-count-prefixed array inside the profile object --
no UE `Size` fields wrap them -- so a rebind is a straight FString splice, no
re-serialization of the tree.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from . import Game
from .steam import libraries

_PROFILE_OBJ_RE = re.compile(r"AcrEnhancedPlayerMappableKeyProfile_\d+$")
_PROFILE_ID_PREFIX = "InputUserSettings.Profiles."

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


def _scan_fstrings(data: bytes) -> list[tuple[int, str, int]]:
    """[(offset, text, byte_len)] for every length-prefixed ASCII FString.
    `offset` points at the int32 length prefix; the whole FString spans
    [offset, offset + byte_len)."""
    out: list[tuple[int, str, int]] = []
    i, n = 0, len(data)
    while i < n - 4:
        length = struct.unpack_from("<i", data, i)[0]
        end = i + 4 + length
        if 2 <= length <= 250 and end <= n and data[end - 1] == 0 \
                and all(32 <= b < 127 for b in data[i + 4:end - 1]):
            out.append((i, data[i + 4:end - 1].decode("latin1"), 4 + length))
            i = end
        else:
            i += 1
    return out


def _fstr(s: str) -> bytes:
    b = s.encode("latin1") + b"\x00"
    return struct.pack("<i", len(b)) + b


def _split_camel(s: str) -> str:
    """'CycleLights' -> 'Cycle Lights' (AC Rally action names are concatenated)."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)


def _active_profile_id(strs: list[tuple[int, str, int]]) -> str | None:
    """`CurrentProfileIdentifier` -> its TagName (e.g.
    'InputUserSettings.Profiles.Current2'), the profile the game reads."""
    for k, (_off, s, _n) in enumerate(strs):
        if s == "CurrentProfileIdentifier":
            for _o2, s2, _n2 in strs[k + 1:k + 12]:
                if s2.startswith(_PROFILE_ID_PREFIX):
                    return s2
    return None


def _profile_runs(strs: list[tuple[int, str, int]]):
    """[(profile_id, [entry...])] -- one per key profile in the file. Each entry
    is {action, hwkey, hw_off, hw_len}. profile_id is the nearest
    `InputUserSettings.Profiles.*` FString before the profile object header."""
    runs = []
    for k, (_off, s, _n) in enumerate(strs):
        if not _PROFILE_OBJ_RE.match(s):
            continue
        pid = next((t for _o, t, _l in reversed(strs[:k]) if t.startswith(_PROFILE_ID_PREFIX)), None)
        entries = []
        j = k + 1
        while j + 3 < len(strs):
            a, hw, ri, sw = strs[j], strs[j + 1], strs[j + 2], strs[j + 3]
            if ri[1] != "RawInput" or sw[1] != "SteeringWheel":
                break
            entries.append(dict(action=a[1], hwkey=hw[1], hw_off=hw[0], hw_len=hw[2]))
            j += 4
        if entries:
            runs.append((pid, entries))
    return runs


def _target_run(strs):
    """The entry list for the active profile (falls back to the only run)."""
    runs = _profile_runs(strs)
    if not runs:
        raise ValueError("no key mappings found in the save")
    active = _active_profile_id(strs)
    for pid, entries in runs:
        if pid == active:
            return entries
    return max(runs, key=lambda r: sum(e["hwkey"] != "None" for e in r[1]))[1]


def read(path: str | Path) -> dict[int, list[str]]:
    """{gamepad button (1-based) -> [in-game action names]} bound to our device."""
    strs = _scan_fstrings(_sav(path).read_bytes())
    result: dict[int, list[str]] = {}
    for e in _target_run(strs):
        m = _DECK_RE.match(e["hwkey"])
        if not m:
            continue
        btn, name = int(m.group(1)), _split_camel(e["action"])
        result.setdefault(btn, [])
        if name not in result[btn]:
            result[btn].append(name)
    return result


def controls(path: str | Path) -> dict:
    """Every bindable action + which of our buttons each is on (bind-to-game UI)."""
    strs = _scan_fstrings(_sav(path).read_bytes())
    entries = _target_run(strs)
    bound = {}
    for e in entries:
        m = _DECK_RE.match(e["hwkey"])
        if m:
            bound[e["action"]] = int(m.group(1))
    return {
        "controls": [e["action"] for e in entries],
        "device_present": True,   # UE derives our key names from VID/PID, no prior registration needed
        "bound": bound,
    }


def write(path: str | Path, control: str, button: int | None) -> dict:
    """Point `control` at our gamepad `button` (1-based), or clear it (button=None).

    Splices the HardwareKey FString(s) in the active profile's mapping array --
    nothing else in the .sav moves. A one-time backup is written. The game must
    be closed (it reads the save at startup and rewrites it on exit).
    """
    sav = _sav(path)
    data = bytearray(sav.read_bytes())
    strs = _scan_fstrings(bytes(data))
    entries = _target_run(strs)

    target = next((e for e in entries if e["action"] == control), None)
    if target is None:
        raise ValueError(f"unknown control {control!r}")

    want = "None" if button is None else f"GenericUSBController_Button{int(button)}_1209_D200"
    edits = [(target["hw_off"], target["hw_off"] + target["hw_len"], _fstr(want))]
    if button is not None:
        for e in entries:
            if e is not target and e["hwkey"] == want:
                edits.append((e["hw_off"], e["hw_off"] + e["hw_len"], _fstr("None")))

    backup = sav.with_suffix(sav.suffix + ".d200x-bak")
    if not backup.exists():
        backup.write_bytes(bytes(data))

    for start, end, nb in sorted(edits, key=lambda x: -x[0]):  # splice back-to-front
        data[start:end] = nb
    sav.write_bytes(bytes(data))
    return {"ok": True, "control": control, "button": button, "backup": str(backup)}


GAME = Game(
    key="ac_rally", label="AC Rally",
    detect=("acr.exe", "Assetto Corsa Rally"),
    find=find, read=read, controls=controls, write=write,
)
