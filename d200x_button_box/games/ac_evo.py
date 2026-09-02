"""Assetto Corsa EVO (Kunos' own engine) -- controls in `Saved Games/ACE/
input_devices.inputdeviceconfiguration`, a length-delimited protobuf.

    File    { repeated Device devices = 1; }
    Device  { Ident ident = 1;  repeated Mapping mappings = 2; }
    Ident   { string name = 1;  string instance_guid = 2;  string product_guid = 5; }
    Mapping { Control control = 1;  uint32 button0 = 2; }   # button0 = gamepad button - 1
    Control { uint32 id = 1;  uint32 kind = 2;  uint32 dir = 3;  ...  uint32 id = 5; }

`Control.id` is the game's stable control id (per in-game action). `Mapping.
button0` is the 0-based gamepad button, omitted when 0 (proto default) -> button
1. `Control.dir` is 1 / 2 for the - / + half of a bipolar ("cycle") control.

The product-guid encodes PID+VID: `{<PID:04X><VID:04X>-0000-0000-0000-PIDVID}`;
our virtual pad (gamepad.py vendor 0x1209 product 0xD200) is
`{D2001209-0000-0000-0000-504944564944}`.
"""

from __future__ import annotations

import struct
from pathlib import Path

from . import Game
from .steam import libraries

_APPID = "3058630"
_CFG_REL = "pfx/drive_c/users/steamuser/Saved Games/ACE/input_devices.inputdeviceconfiguration"
_DECK_GUID = "{D2001209-0000-0000-0000-504944564944}"

# game control id -> in-game action name (from real bindings; unknown -> "control N")
_CONTROL_IDS: dict[int, str] = {
    120: "Cycle Lights",
    121: "Flashing Lights",
    132: "Indicator Left",
    133: "Indicator Right",
    134: "Hazards",
    136: "Ignition",
    137: "Starter",
    139: "Horn",
    159: "Cycle Nameplate Visibility",
    520: "Toggle HUD",
    525: "Reset Car",
    1703: "ERS Overtake",
    1704: "DRS Activate",
}
_DIR_SUFFIX = {1: " -", 2: " +"}


def find() -> str | None:
    for lib in libraries():
        cfg = lib / "compatdata" / _APPID / _CFG_REL
        if cfg.is_file():
            return str(cfg)
    return None


# --- minimal protobuf reader (wire types 0 varint, 2 length-delimited) ------- #
def _varint(d: bytes, i: int) -> tuple[int, int]:
    val = shift = 0
    while True:
        b = d[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7


def _fields(d: bytes, i: int, end: int):
    """Yield (field_number, wire_type, value, next_index)."""
    while i < end:
        tag, i = _varint(d, i)
        fn, wt = tag >> 3, tag & 7
        if wt == 0:
            v, i = _varint(d, i)
            yield fn, wt, v, i
        elif wt == 2:
            ln, i = _varint(d, i)
            yield fn, wt, d[i:i + ln], i + ln
            i += ln
        elif wt == 5:
            i += 4
        elif wt == 1:
            i += 8
        else:
            raise ValueError(f"bad protobuf wire type {wt}")


def _cfg_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_file():
        return p
    for c in (p / _CFG_REL, p / "compatdata" / _APPID / _CFG_REL):
        if c.is_file():
            return c
    raise FileNotFoundError(f"input_devices.inputdeviceconfiguration not found under {path}")


def read(path: str | Path) -> dict[int, list[str]]:
    """{gamepad button (1-based) -> [in-game action names]} bound to our device."""
    data = _cfg_path(path).read_bytes()
    result: dict[int, list[str]] = {}
    for fn, _wt, dev, _ni in _fields(data, 0, len(data)):
        if fn != 1:
            continue
        is_ours = False
        rows = []
        for f2, _w2, v2, _n2 in _fields(dev, 0, len(dev)):
            if f2 == 1:  # ident
                for f3, w3, v3, _n3 in _fields(v2, 0, len(v2)):
                    if f3 == 5 and w3 == 2 and v3.decode("latin1", "ignore") == _DECK_GUID:
                        is_ours = True
            elif f2 == 2:  # a mapping
                cid = direction = None
                button0 = 0
                for f4, w4, v4, _n4 in _fields(v2, 0, len(v2)):
                    if f4 == 1 and w4 == 2:
                        for f5, _w5, v5, _n5 in _fields(v4, 0, len(v4)):
                            if f5 == 1:
                                cid = v5
                            elif f5 == 3:
                                direction = v5
                    elif f4 == 2:
                        button0 = v4
                rows.append((cid, direction, button0))
        if not is_ours:
            continue
        for cid, direction, button0 in rows:
            if cid is None:
                continue
            name = _CONTROL_IDS.get(cid, f"control {cid}") + _DIR_SUFFIX.get(direction, "")
            btn = button0 + 1
            result.setdefault(btn, [])
            if name not in result[btn]:
                result[btn].append(name)
    return result


GAME = Game(
    key="ac_evo", label="AC EVO",
    detect=("AssettoCorsaEVO", "acevo"), find=find, read=read,
)
