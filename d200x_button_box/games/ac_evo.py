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

`write()` splices only our device's mapping list -- every other device and
mapping is kept byte-for-byte -- and can rebind the named controls (`_CONTROL_
IDS`). Unnamed controls can't be written (no id known); import them back after
binding in-game.
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


# --- minimal protobuf *writer* (varint + length-delimited only) ------------- #
def _vb(n: int) -> bytes:
    out = b""
    while True:
        b, n = n & 0x7F, n >> 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _fv(fn: int, val: int) -> bytes:                 # varint field
    return _vb(fn << 3) + _vb(val)


def _fb(fn: int, payload: bytes) -> bytes:            # length-delimited field
    return _vb((fn << 3) | 2) + _vb(len(payload)) + payload


def _control_bytes(m: bytes) -> bytes | None:
    """The Control sub-message's value bytes from one Mapping's value bytes."""
    for f, w, v, _n in _fields(m, 0, len(m)):
        if f == 1 and w == 2:
            return v
    return None


def _mapping_control(m: bytes):
    """(control_id, direction, button0) of one Mapping's value bytes."""
    cid = direction = None
    button0 = 0
    ctl = _control_bytes(m)
    if ctl is not None:
        for f5, _w5, v5, _n5 in _fields(ctl, 0, len(ctl)):
            if f5 == 1:
                cid = v5
            elif f5 == 3:
                direction = v5
    for f, w, v, _n in _fields(m, 0, len(m)):
        if f == 2 and w == 0:
            button0 = v
    return cid, direction, button0


def _split_device(dev: bytes):
    """(non-mapping fields re-serialised, [Mapping value bytes], is_ours)."""
    keep = b""
    mappings: list[bytes] = []
    is_ours = False
    for f, w, v, _n in _fields(dev, 0, len(dev)):
        if f == 2 and w == 2:
            mappings.append(v)
        elif w == 2:
            keep += _fb(f, v)
            if f == 1:
                for f3, w3, v3, _n3 in _fields(v, 0, len(v)):
                    if f3 == 5 and w3 == 2 and v3.decode("latin1", "ignore") == _DECK_GUID:
                        is_ours = True
        else:
            keep += _fv(f, v)
    return keep, mappings, is_ours


def _our_mappings(path: str | Path):
    data = _cfg_path(path).read_bytes()
    for fn, _wt, dev, _ni in _fields(data, 0, len(data)):
        if fn != 1:
            continue
        _keep, mappings, is_ours = _split_device(dev)
        if is_ours:
            return data, mappings
    return data, None


def read(path: str | Path) -> dict[int, list[str]]:
    """{gamepad button (1-based) -> [in-game action names]} bound to our device."""
    _data, mappings = _our_mappings(path)
    result: dict[int, list[str]] = {}
    for m in mappings or []:
        cid, direction, button0 = _mapping_control(m)
        if cid is None:
            continue
        name = _CONTROL_IDS.get(cid, f"control {cid}") + _DIR_SUFFIX.get(direction, "")
        result.setdefault(button0 + 1, [])
        if name not in result[button0 + 1]:
            result[button0 + 1].append(name)
    return result


_NAME_TO_ID = {v: k for k, v in _CONTROL_IDS.items()}


def controls(path: str | Path) -> dict:
    """Bindable control names + which of our buttons each is currently on."""
    bound = {names[0]: btn for btn, names in read(path).items() if names[0] in _NAME_TO_ID}
    return {
        "controls": list(_CONTROL_IDS.values()),
        "device_present": True,   # our key names are synthetic; no prior registration needed
        "bound": bound,
    }


def write(path: str | Path, control: str, button: int | None) -> dict:
    """Point `control` (a name from `controls()`) at our gamepad `button`
    (1-based), or clear it (button=None). Splices only our device's mapping
    list; every other device and mapping is kept byte-for-byte. Game must be
    closed -- AC EVO reads this file at startup."""
    cfg = _cfg_path(path)
    data = cfg.read_bytes()
    cid = _NAME_TO_ID.get(control)
    if cid is None:
        raise ValueError(f"cannot write unnamed control {control!r}")

    out = b""
    hit = False
    for fn, _wt, dev, _ni in _fields(data, 0, len(data)):
        if fn != 1:
            out += _fv(fn, dev) if isinstance(dev, int) else _fb(fn, dev)
            continue
        keep, mappings, is_ours = _split_device(dev)
        if not is_ours or hit:          # only touch the first block that's ours
            out += _fb(1, dev)
            continue
        hit = True
        kept = []
        existing_ctl = None
        for m in mappings:
            if _mapping_control(m)[0] == cid:
                existing_ctl = _control_bytes(m)   # reuse the exact Control bytes on a rebind
            else:
                kept.append(m)                     # every other mapping stays byte-for-byte
        if button is not None:
            ctl = existing_ctl if existing_ctl is not None else _fv(1, cid) + _fv(2, 1) + _fv(5, cid)
            mapping = _fb(1, ctl) + (_fv(2, button - 1) if button > 1 else b"")
            kept.append(mapping)
        out += _fb(1, keep + b"".join(_fb(2, m) for m in kept))

    if not hit:
        raise ValueError(
            "the D200x Button Box is not in AC EVO's config yet -- bind any one "
            "control to it in-game once first")

    backup = cfg.with_suffix(cfg.suffix + ".d200x-bak")
    if not backup.exists():
        backup.write_bytes(data)
    cfg.write_bytes(out)
    return {"ok": True, "control": control, "button": button, "backup": str(backup)}


GAME = Game(
    key="ac_evo", label="AC EVO",
    detect=("AssettoCorsaEVO", "acevo"), find=find, read=read,
    controls=controls, write=write,
)
