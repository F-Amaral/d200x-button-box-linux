"""Suppress the D200x's own firmware HID keyboard.

Interface 1 of the deck is a real HID keyboard: keys programmed in Ulanzi Studio
(including the factory demo macros) are typed straight from firmware and reach
the desktop with nothing running. While we drive the deck as a gamepad off
interface 0 we grab those evdev nodes so the keystrokes -- and any global
shortcuts they would trigger -- go nowhere.
"""

from __future__ import annotations

import logging

import evdev

from . import protocol

log = logging.getLogger(__name__)


def find_keyboards() -> list[evdev.InputDevice]:
    """Every evdev node that belongs to the D200x (keyboard + consumer-control)."""
    found: list[evdev.InputDevice] = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        info = dev.info
        if info.vendor == protocol.VENDOR_ID and info.product == protocol.PRODUCT_ID:
            found.append(dev)
        else:
            dev.close()
    return found


class KeyboardSink:
    """Context manager: EVIOCGRAB the deck's keyboard nodes, ungrab on exit."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._grabbed: list[evdev.InputDevice] = []

    def __enter__(self) -> "KeyboardSink":
        if not self.enabled:
            return self
        devs = find_keyboards()
        if not devs:
            log.warning(
                "D200x keyboard evdev node not found -- firmware key macros will "
                "still reach the desktop. Install the SUBSYSTEM==\"input\" udev "
                "line and replug, or add yourself to the 'input' group."
            )
            return self
        for dev in devs:
            try:
                dev.grab()
                self._grabbed.append(dev)
                log.info("grabbed %s (%s)", dev.path, dev.name)
            except OSError as e:
                log.warning("could not grab %s: %s", dev.path, e)
                dev.close()
        if self._grabbed:
            log.info("firmware key macros suppressed while running")
        return self

    def __exit__(self, *_exc) -> None:
        for dev in self._grabbed:
            try:
                dev.ungrab()
            except OSError:
                pass
            dev.close()
        self._grabbed.clear()
