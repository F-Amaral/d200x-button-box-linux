"""Event-routing check for the daemon, with fake device + gamepad."""

import time

from d200x_button_box.config import Config
from d200x_button_box.daemon import Daemon
from d200x_button_box.protocol import InputEvent


class FakePad:
    def __init__(self):
        self.events = []  # ("press"|"release", button)

    def press(self, b):
        self.events.append(("press", b))

    def release(self, b):
        self.events.append(("release", b))

    def close(self):
        pass


def _daemon(keys=None, knobs=None):
    cfg = Config(keys=keys or {}, knobs=knobs or {}, pulse_ms=10)
    pad = FakePad()
    return Daemon(cfg, dev=object(), pad=pad), pad


def test_key_press_release_maps_to_hold():
    d, pad = _daemon(keys={3: {"gamepad": 7}})
    d._on_event(InputEvent(3, "key", "press", b""))
    d._on_event(InputEvent(3, "key", "release", b""))
    assert pad.events == [("press", 7), ("release", 7)]


def test_unmapped_key_is_ignored():
    d, pad = _daemon(keys={3: {"gamepad": 7}})
    d._on_event(InputEvent(9, "key", "press", b""))
    assert pad.events == []


def test_momentary_key_pulses():
    d, pad = _daemon(keys={2: {"gamepad": 4, "momentary": True}})
    d._on_event(InputEvent(2, "key", "press", b""))
    assert pad.events == [("press", 4)]
    time.sleep(0.02)
    d._drain_pending()
    assert pad.events == [("press", 4), ("release", 4)]


def test_knob_turn_pulses_then_releases():
    d, pad = _daemon(knobs={17: {"left": {"gamepad": 15}, "right": {"gamepad": 16}}})
    d._on_event(InputEvent(17, "knob", "right", b""))
    assert pad.events == [("press", 16)]
    time.sleep(0.02)
    d._drain_pending()
    assert pad.events[-1] == ("release", 16)


def test_knob_click_pulses_and_ignores_release():
    d, pad = _daemon(knobs={18: {"press": {"gamepad": 20}}})
    d._on_event(InputEvent(18, "knob", "press", b""))
    d._on_event(InputEvent(18, "knob", "release", b""))  # firmware bundles this
    assert pad.events == [("press", 20)]
    time.sleep(0.02)
    d._drain_pending()
    assert pad.events == [("press", 20), ("release", 20)]


def test_out_of_range_button_does_not_crash():
    d, pad = _daemon(keys={0: {"gamepad": 999}})
    d.pad = _RaisingPad()
    d._on_event(InputEvent(0, "key", "press", b""))  # logged, not raised


class _RaisingPad(FakePad):
    def press(self, b):
        raise ValueError("out of range")
