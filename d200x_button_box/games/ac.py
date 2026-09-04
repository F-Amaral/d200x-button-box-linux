"""Assetto Corsa (the original) -- controller bindings in
`compatdata/244210/pfx/…/Documents/Assetto Corsa/cfg/controls.ini`.

Plain INI, CRLF. A button action is a section with `BUTTON=` + `JOY=` (`-1` =
unbound); axes (`STEER`, `THROTTLE`, …) carry `AXLE=` instead and are skipped.
`JOY` indexes `[CONTROLLERS]` (`CONn` / `PGUIDn`); `BUTTON` is the 0-based
DirectInput button, so `BUTTON = our gamepad button - 1`.

`[CONTROLLERS]` only lists a device once you've bound something to it in-game,
so -- like LMU / AC Rally -- bind any one control to the deck in AC's controls
menu first. Our virtual pad's product GUID is
`D2001209-0000-0000-0000-504944564944` (PID 0xD200, VID 0x1209).

Covers Content Manager / CSP too: the `__EXT_*` and `__CM_*` sections use the
same `BUTTON` / `JOY`.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import Game
from .steam import libraries

_APPID = "244210"
_CFG_REL = "pfx/drive_c/users/steamuser/Documents/Assetto Corsa/cfg/controls.ini"
_DECK_PGUID = "D2001209-0000-0000-0000-504944564944"

# section name -> friendly label; anything else is de-prefixed + title-cased
_NICE = {
    "ABSDN": "ABS -", "ABSUP": "ABS +", "TCDN": "TC -", "TCUP": "TC +",
    "BALANCEDN": "Brake Bias Rear", "BALANCEUP": "Brake Bias Front",
    "ENGINE_BRAKE_DN": "Engine Brake -", "ENGINE_BRAKE_UP": "Engine Brake +",
    "TURBODN": "Turbo -", "TURBOUP": "Turbo +",
    "GEARDN": "Gear Down", "GEARUP": "Gear Up",
    "KERS": "KERS", "DRS": "DRS", "MGUH_MODE": "MGU-H Mode",
    "MGUK_DELIVERY_DN": "MGU-K Delivery -", "MGUK_DELIVERY_UP": "MGU-K Delivery +",
    "MGUK_RECOVERY_DN": "MGU-K Recovery -", "MGUK_RECOVERY_UP": "MGU-K Recovery +",
    "ACTION_HEADLIGHTS": "Headlights", "ACTION_HEADLIGHTS_FLASH": "Flash Lights",
    "ACTION_HORN": "Horn", "ACTION_CHANGE_CAMERA": "Change Camera",
    "GLANCELEFT": "Look Left", "GLANCERIGHT": "Look Right", "GLANCEBACK": "Look Back",
    "HANDBRAKE": "Handbrake", "STARTER": "Starter", "RESET_RACE": "Reset Race",
    "ACTIVATE_AI": "Activate AI", "IDEAL_LINE": "Ideal Line",
    "NEXT_CAR": "Next Car", "PREVIOUS_CAR": "Previous Car", "PLAYER_CAR": "Player Car",
    "__EXT_PIT_LIMITER": "Pit Limiter", "__EXT_SPEED_LIMITER": "Speed Limiter",
    "__EXT_HAZARDS": "Hazards", "__EXT_TURNSIGNAL_LEFT": "Indicator Left",
    "__EXT_TURNSIGNAL_RIGHT": "Indicator Right", "__EXT_TURNSIGNAL_CANCEL": "Indicator Cancel",
    "__EXT_STARTER": "Ignition / Starter", "__EXT_LOW_BEAM": "Low Beam",
    "__EXT_WIPERS_MORE": "Wipers +", "__EXT_WIPERS_LESS": "Wipers -", "__EXT_WIPERS_OFF": "Wipers Off",
    "__EXT_LOOK_LEFT": "Look Left (CSP)", "__EXT_LOOK_RIGHT": "Look Right (CSP)", "__EXT_LOOK_BACK": "Look Back (CSP)",
    "__EXT_ENGINEMAP_UP": "Engine Map +", "__EXT_MANUAL_CUTOFF": "Manual Cutoff",
    "__EXT_TELLTALE_RESET": "Reset Telltale", "__EXT_HIDE_UI": "Hide UI",
    "__EXT_TC2_UP": "TC2 +", "__EXT_TC2_DOWN": "TC2 -",
}


def _label(section: str) -> str:
    if section in _NICE:
        return _NICE[section]
    s = re.sub(r"^(__EXT_|__CM_|ACTION_)", "", section)
    return s.replace("_", " ").title()


_NAME_TO_SECTION: dict[str, str] = {}   # built lazily from whatever a file has


def find() -> str | None:
    for lib in libraries():
        cfg = lib / "compatdata" / _APPID / _CFG_REL
        if cfg.is_file():
            return str(cfg)
    return None


def _cfg(path: str | Path) -> Path:
    p = Path(path)
    if p.is_file():
        return p
    for c in (p / _CFG_REL, p / "compatdata" / _APPID / _CFG_REL):
        if c.is_file():
            return c
    raise FileNotFoundError(f"controls.ini not found under {path}")


def _read(path: str | Path) -> str:
    """Raw text, newlines untouched (the file is CRLF; keep it that way)."""
    return _cfg(path).read_bytes().decode("utf-8", "replace")


def _sections(text: str) -> dict[str, dict[str, str]]:
    """{section: {key: value}} -- values stripped of any '; comment' tail."""
    out: dict[str, dict[str, str]] = {}
    cur: dict[str, str] | None = None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"\[(.+)\]$", line)
        if m:
            cur = out.setdefault(m.group(1), {})
        elif cur is not None and "=" in line:
            k, _, v = line.partition("=")
            cur[k.strip()] = v.split(";")[0].strip()
    return out


def _our_joy(secs: dict[str, dict[str, str]]) -> int | None:
    ctl = secs.get("CONTROLLERS", {})
    for k, v in ctl.items():
        if k.startswith("PGUID") and v.upper() == _DECK_PGUID:
            try:
                return int(k[5:])
            except ValueError:
                return None
    return None


def _button_actions(secs: dict[str, dict[str, str]]):
    """(section, joy, button) for every bindable button action (skips axes)."""
    for name, kv in secs.items():
        if name == "CONTROLLERS" or "AXLE" in kv or "BUTTON" not in kv or "JOY" not in kv:
            continue
        try:
            yield name, int(kv["JOY"]), int(kv["BUTTON"])
        except ValueError:
            continue


def read(path: str | Path) -> dict[int, list[str]]:
    """{gamepad button (1-based) -> [in-game action names]} on our device."""
    secs = _sections(_read(path))
    joy = _our_joy(secs)
    result: dict[int, list[str]] = {}
    if joy is None:
        return result
    for name, j, btn in _button_actions(secs):
        if j == joy and btn >= 0:
            result.setdefault(btn + 1, []).append(_label(name))
    return result


def controls(path: str | Path) -> dict:
    secs = _sections(_read(path))
    joy = _our_joy(secs)
    _NAME_TO_SECTION.clear()
    names, bound = [], {}
    for name, j, btn in sorted(_button_actions(secs), key=lambda t: _label(t[0])):
        lbl = _label(name)
        _NAME_TO_SECTION[lbl] = name
        names.append(lbl)
        if joy is not None and j == joy and btn >= 0:
            bound[lbl] = btn + 1
    return {
        "controls": names,
        "device_present": joy is not None,
        "bound": bound,
    }


def write(path: str | Path, control: str, button: int | None) -> dict:
    """Point `control` at our gamepad `button` (1-based), or clear it. Rewrites
    only the target action's `BUTTON` / `JOY` lines (and clears a conflicting
    binding on the same button). AC must be closed -- it reads controls.ini at
    startup and rewrites it on exit."""
    cfg = _cfg(path)
    text = cfg.read_bytes().decode("utf-8", "replace")
    secs = _sections(text)
    joy = _our_joy(secs)
    if joy is None:
        raise ValueError("the D200x Button Box is not in AC's config yet -- bind any "
                         "one control to it in AC's controls menu first")
    if not _NAME_TO_SECTION:
        controls(cfg)
    section = _NAME_TO_SECTION.get(control) or (control if control in secs else None)
    if section is None:
        raise ValueError(f"unknown control {control!r}")

    b0 = -1 if button is None else int(button) - 1
    # sections to rewrite: the target, plus any other one currently on that button
    targets = {section: (b0, -1 if button is None else joy)}
    if button is not None:
        for name, j, btn in _button_actions(secs):
            if name != section and j == joy and btn == b0:
                targets[name] = (-1, -1)

    lines = text.split("\n")
    cur = None
    for i, raw in enumerate(lines):
        m = re.match(r"\[(.+)\]\s*$", raw.strip())
        if m:
            cur = m.group(1)
            continue
        if cur in targets:
            key, _, _ = raw.partition("=")
            k = key.strip()
            eol = "\r" if raw.endswith("\r") else ""
            if k == "BUTTON":
                lines[i] = f"BUTTON={targets[cur][0]}{eol}"
            elif k == "JOY":
                lines[i] = f"JOY={targets[cur][1]}{eol}"

    backup = cfg.with_suffix(cfg.suffix + ".d200x-bak")
    if not backup.exists():
        backup.write_bytes(text.encode("utf-8", "replace"))
    cfg.write_bytes("\n".join(lines).encode("utf-8", "replace"))
    return {"ok": True, "control": control, "button": button, "backup": str(backup)}


GAME = Game(
    key="ac", label="Assetto Corsa",
    detect=("acs.exe",),   # the game exe; Content Manager alone shouldn't trigger it
    find=find, read=read, controls=controls, write=write,
)
