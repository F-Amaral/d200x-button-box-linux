"""A virtual gamepad games can bind -- including Windows titles under Proton/Wine.

Implemented with `uinput` via python-evdev. The kernel joystick layer (joydev)
exposes the BTN_TRIGGER_HAPPY* range as plain joystick buttons, and SDL / Wine's
dinput see the resulting `/dev/input/js*` + `event*` node like any real pad.
"""

from __future__ import annotations

import logging

from evdev import UInput
from evdev import ecodes as e

log = logging.getLogger(__name__)

_BASE = e.BTN_TRIGGER_HAPPY1  # 0x2c0
MAX_BUTTONS = 40              # BTN_TRIGGER_HAPPY1..40


class Gamepad:
    def __init__(self, n_buttons: int = 32, name: str = "D200x Button Box") -> None:
        self._n = max(1, min(int(n_buttons), MAX_BUTTONS))
        caps = {e.EV_KEY: [_BASE + i for i in range(self._n)]}
        self._ui = UInput(caps, name=name, vendor=0x1209, product=0xD200, version=1)
        log.info("virtual gamepad %r ready (%d buttons)", name, self._n)

    def _code(self, button: int) -> int:
        if not 1 <= button <= self._n:
            raise ValueError(f"gamepad button {button} out of range 1..{self._n}")
        return _BASE + button - 1

    def press(self, button: int) -> None:
        self._ui.write(e.EV_KEY, self._code(button), 1)
        self._ui.syn()

    def release(self, button: int) -> None:
        self._ui.write(e.EV_KEY, self._code(button), 0)
        self._ui.syn()

    def close(self) -> None:
        try:
            self._ui.close()
        except Exception:
            pass
