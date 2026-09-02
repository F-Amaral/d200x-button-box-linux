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
mapping is kept byte-for-byte. It can bind any control id, named or not:
`controls()` lists our named set plus every id with a default keyboard binding
(read from the sibling `input_keyboard.*` file, same schema). Ids without a
name show as `control <id>`.

Names are learned, not hard-coded past the initial set: `learn()` takes the
labels you put on deck keys and remembers them per control id in
`CONFIG_DIR/game_names.yaml`, which overlays `_CONTROL_IDS`. So the flow is:
bind a control to a deck key, label the key, done -- the name sticks and shows
everywhere. `tools/acevo-probe.py` bulk-binds the unknowns for one discovery
pass if you'd rather name them all at once.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from . import Game
from .steam import libraries

_APPID = "3058630"
_SAVE_DIR = "pfx/drive_c/users/steamuser/Saved Games/ACE"
_CFG_REL = f"{_SAVE_DIR}/input_devices.inputdeviceconfiguration"
_KBD_REL = f"{_SAVE_DIR}/input_keyboard.keyboardinputconfiguration"
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

# learned names -- {control id: action name}, filled from the labels you put on
# deck keys in an AC EVO profile (daemon._sync_game_labels -> learn()). Overlays
# _CONTROL_IDS so the bind dropdown / read() show real names with no code change.
# Stored in CONFIG_DIR/game_names.yaml under `ac_evo:`.
_LEARNED: dict = {"mtime": -1.0, "map": {}}


def _names_path() -> Path:
    from ..config import CONFIG_DIR
    return CONFIG_DIR / "game_names.yaml"


def _learned() -> dict[int, str]:
    p = _names_path()
    try:
        m = p.stat().st_mtime
    except OSError:
        _LEARNED.update(mtime=-1.0, map={})
        return {}
    if m != _LEARNED["mtime"]:
        import yaml
        raw = (yaml.safe_load(p.read_text()) if p.is_file() else {}) or {}
        _LEARNED["map"] = {int(k): str(v) for k, v in (raw.get("ac_evo") or {}).items() if v}
        _LEARNED["mtime"] = m
    return _LEARNED["map"]


def _names() -> dict[int, str]:
    return {**_CONTROL_IDS, **_learned()}


def _name_to_id() -> dict[str, int]:
    return {v: k for k, v in _names().items()}


def _remember(new: dict[int, str]) -> None:
    """Merge {control id: name} into game_names.yaml. Won't overwrite an id that
    already has a name there."""
    import yaml

    p = _names_path()
    raw = (yaml.safe_load(p.read_text()) if p.is_file() else {}) or {}
    cur = {int(k): v for k, v in (raw.get("ac_evo") or {}).items()}
    added = {k: v for k, v in new.items() if int(k) not in cur}
    if not added:
        return
    cur.update(added)
    raw["ac_evo"] = {k: cur[k] for k in sorted(cur)}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    _LEARNED["mtime"] = -1.0


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
        name = _control_name(cid, direction)
        result.setdefault(button0 + 1, [])
        if name not in result[button0 + 1]:
            result[button0 + 1].append(name)
    return result


def _control_name(cid: int, direction: int | None = None) -> str:
    return _names().get(cid, f"control {cid}") + _DIR_SUFFIX.get(direction, "")


def _resolve_control(name: str):
    """A name from `controls()` -> (control_id, direction) or (None, None).
    Accepts a named control, a `control <id>` placeholder, and a trailing
    ` +` / ` -` for the halves of a bipolar cycle control."""
    name = name.strip()
    direction = None
    if name.endswith((" +", " -")):
        name, direction = name[:-2].rstrip(), (2 if name.endswith("+") else 1)
    n2i = _name_to_id()
    if name in n2i:
        return n2i[name], direction
    m = re.fullmatch(r"control (\d+)", name)
    return (int(m.group(1)), direction) if m else (None, None)


def learn(path: str | Path, labels: dict[int, str]) -> None:
    """`labels` is {gamepad button (1-based): the human label on that deck key}.
    For every button carrying a control we have no name for, remember its label
    as the name (so the dropdown / import stop showing `control <id>`). Bipolar
    (+/-) controls are skipped -- their name is ambiguous per half."""
    if _names_path().with_name(".acevo_probe.json").exists():
        return   # a probe pass is live -- its bindings aren't real, don't learn from them
    _data, mappings = _our_mappings(path)
    known = _names()
    add: dict[int, str] = {}
    for m in mappings or []:
        cid, direction, button0 = _mapping_control(m)
        if cid is None or direction is not None or cid in known:
            continue
        label = (labels.get(button0 + 1) or "").strip()
        if label and not re.fullmatch(r"control \d+", label):
            add[cid] = label
    if add:
        _remember(add)


def _blob_ids(data: bytes) -> set[int]:
    """Every control id bound to any device in an input config blob -- handles
    both the nested `Device{ Mapping }` layout (input_devices.*) and the
    keyboard file's flat `Mapping` list (field 1 there is a header, not a
    device -- parsing it as one fails harmlessly)."""
    ids: set[int] = set()
    for fn, wt, val, _ni in _fields(data, 0, len(data)):
        if wt != 2:
            continue
        if fn == 2:                                   # a top-level Mapping (keyboard file)
            cid = _mapping_control(val)[0]
            if cid is not None:
                ids.add(cid)
        elif fn == 1:                                 # a Device -> scan its Mappings
            try:
                for f, w, m, _n in _fields(val, 0, len(val)):
                    if f == 2 and w == 2:
                        cid = _mapping_control(m)[0]
                        if cid is not None:
                            ids.add(cid)
            except (IndexError, ValueError):
                pass                                  # not a device submessage
    return ids


def _known_ids(cfg: Path) -> list[int]:
    """Every control id we can name or bind: our set + every id bound to *any*
    device in the config (wheel, pad, keyboard). Controls nobody has bound
    anywhere aren't listed -- bind one in-game and it shows up."""
    ids = set(_names()) | _blob_ids(cfg.read_bytes())
    kbd = cfg.parent / "input_keyboard.keyboardinputconfiguration"
    if kbd.is_file():
        ids |= _blob_ids(kbd.read_bytes())
    return sorted(ids)


def controls(path: str | Path) -> dict:
    """Bindable control names + which of our buttons each is currently on.
    The list is everything the game knows; ids we don't have a name for show as
    `control <id>` and are still bindable (test in-game, then name in code)."""
    cfg = _cfg_path(path)
    bound = {names[0]: btn for btn, names in read(cfg).items()}
    return {
        "controls": [_control_name(c) for c in _known_ids(cfg)],
        "device_present": True,   # our key names are synthetic; no prior registration needed
        "bound": bound,
    }


def write(path: str | Path, control: str, button: int | None) -> dict:
    """Point `control` (a name from `controls()`, or `control <id>`) at our
    gamepad `button` (1-based), or clear it (button=None). Splices only our
    device's mapping list; every other device and mapping is kept
    byte-for-byte. Game must be closed -- AC EVO reads this file at startup."""
    cfg = _cfg_path(path)
    data = cfg.read_bytes()
    cid, direction = _resolve_control(control)
    if cid is None:
        raise ValueError(f"cannot resolve control {control!r}")

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
            mc = _mapping_control(m)
            if mc[0] == cid and mc[1] == direction:
                existing_ctl = _control_bytes(m)   # reuse the exact Control bytes on a rebind
            else:
                kept.append(m)                     # every other mapping stays byte-for-byte
        if button is not None:
            ctl = existing_ctl if existing_ctl is not None else (
                _fv(1, cid) + _fv(2, 1) + (_fv(3, direction) if direction else b"") + _fv(5, cid))
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
    controls=controls, write=write, learn=learn,
)
