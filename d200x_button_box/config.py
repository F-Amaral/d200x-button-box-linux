"""YAML config: which deck control drives which gamepad button / key / command."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import protocol

DEFAULT_PATH = Path.home() / ".config" / "d200x-button-box" / "config.yaml"

# A binding is a dict with exactly one of:
#   {gamepad: N}            press deck control -> hold gamepad button N (release on release)
#   {gamepad: N, momentary: true}   press -> short pulse of button N (good for toggles)
#   {key: "F1"}             press -> send a keystroke via ydotool/xdotool
#   {command: "shell ..."}  press -> run a shell command
# Knob turn events (left/right) always fire as a short pulse.


@dataclass
class Config:
    gamepad_name: str = "D200x Button Box"
    gamepad_buttons: int = 32
    brightness: int | None = 80
    heartbeat_seconds: float = 2  # watchdog write interval that holds host mode; 0 = off
    pulse_ms: int = 60            # how long a knob step / momentary button is held
    grab_keyboard: bool = True  # swallow the deck's firmware HID keyboard (interface 1)
    keys: dict[int, dict] = field(default_factory=dict)   # control index -> binding
    knobs: dict[int, dict] = field(default_factory=dict)  # control index -> {left/right/press/release: binding}

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Config":
        path = Path(path or DEFAULT_PATH)
        raw = (yaml.safe_load(path.read_text()) if path.exists() else {}) or {}
        c = cls(
            gamepad_name=raw.get("gamepad_name", cls.gamepad_name),
            gamepad_buttons=int(raw.get("gamepad_buttons", cls.gamepad_buttons)),
            brightness=raw.get("brightness", cls.brightness),
            heartbeat_seconds=float(raw.get("heartbeat_seconds", cls.heartbeat_seconds)),
            pulse_ms=int(raw.get("pulse_ms", cls.pulse_ms)),
            grab_keyboard=bool(raw.get("grab_keyboard", cls.grab_keyboard)),
        )
        for k, v in (raw.get("keys") or {}).items():
            c.keys[int(k)] = v or {}
        for k, v in (raw.get("knobs") or {}).items():
            c.knobs[int(k)] = v or {}
        return c


def default_yaml() -> str:
    """Starter config: every D200x control mapped to a sequential gamepad button."""
    out = [
        "# D200x Button Box -- mapping config",
        "# Each deck control fires a virtual gamepad button that LMU / AC Evo can bind",
        "# in their normal controller settings. Binding forms:",
        '#   {gamepad: N}   {gamepad: N, momentary: true}   {key: "F1"}   {command: "sh -c ..."}',
        '# Add  label: "PIT"  to a key binding to print text on that LCD key.',
        "",
        "gamepad_name: D200x Button Box",
        "gamepad_buttons: 32",
        "brightness: 80",
        "heartbeat_seconds: 2   # watchdog write interval that keeps the deck in host mode",
        "pulse_ms: 40",
        "grab_keyboard: true    # swallow the deck's factory keyboard macros (interface 1)",
        "",
        "keys:",
    ]
    btn = 1
    indices = [*range(13), protocol.STATUS_KEY_INDEX, *protocol.PAGE_KEY_INDICES]
    for i in indices:
        tag = {
            protocol.STATUS_KEY_INDEX: "wide status key",
            protocol.PAGE_KEY_INDICES[0]: "aux button left of encoders",
            protocol.PAGE_KEY_INDICES[1]: "aux button right of encoders",
        }.get(i, f"LCD key {i}")
        out.append(f"  {i}: {{gamepad: {btn}}}   # {tag}")
        btn += 1
    out += ["", "knobs:"]
    for i in protocol.KNOB_INDICES:
        out.append(f"  {i}:                       # rotary encoder {i}")
        out.append(f"    left:  {{gamepad: {btn}}}")
        out.append(f"    right: {{gamepad: {btn + 1}}}")
        out.append(f"    press: {{gamepad: {btn + 2}}}")
        btn += 3
    out.append("")
    return "\n".join(out)
