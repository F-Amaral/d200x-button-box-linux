"""Talk to the D200x through the kernel `hidraw` node directly.

No external HID library: hidapi's PyPI wheel ships the libusb backend, which on
this hardware opens interface 0 but never delivers the interrupt-IN reports (and
throws "read error"). Reading `/dev/hidrawN` ourselves is a dozen lines and just
works. Writes prepend a 0x00 report-ID byte, as the device expects.

A read or write that fails with a fatal error (device unplugged / re-enumerated)
raises `DeviceGone` so the daemon can drop the handle and reconnect.
"""

from __future__ import annotations

import errno
import glob
import logging
import os
import re
import select
import time
from collections.abc import Iterator

from . import protocol

log = logging.getLogger(__name__)

# uevent line looks like:  HID_ID=0003:00002207:00000019
_HID_ID_RE = re.compile(
    rf"^HID_ID=[0-9A-Fa-f]+:0*{protocol.VENDOR_ID:X}:0*{protocol.PRODUCT_ID:X}$",
    re.MULTILINE,
)
_IFACE_RE = re.compile(r"\d+-[\d.]+:\d+\.(\d+)/")

_NOT_FOUND = (
    "No hidraw node for the D200x (2207:0019). Check `lsusb`; if the deck shows "
    "as on but nothing appears under /sys/class/hidraw, try another USB port "
    "(ideally a USB 2.0 one straight off the motherboard)."
)

# errnos that mean "transient, nothing to read" vs. "the handle is dead"
_TRANSIENT = {errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR}


class DeviceGone(Exception):
    """The hidraw handle is no longer usable (unplug / re-enumeration)."""


def _iface_of(hidraw_sysfs: str) -> int | None:
    """USB interface number backing a /sys/class/hidraw/hidrawN entry."""
    m = _IFACE_RE.search(os.path.realpath(hidraw_sysfs) + "/")
    return int(m.group(1)) if m else None


def list_hidraw() -> list[tuple[str, int | None]]:
    """[(‹/dev/hidrawN›, interface_number)] for every D200x HID interface."""
    out: list[tuple[str, int | None]] = []
    for sysfs in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            uevent = open(os.path.join(sysfs, "device", "uevent")).read()
        except OSError:
            continue
        if _HID_ID_RE.search(uevent):
            out.append(("/dev/" + os.path.basename(sysfs), _iface_of(sysfs)))
    return out


def find_hidraw(interface: int = protocol.PROTOCOL_INTERFACE) -> str | None:
    nodes = list_hidraw()
    for path, iface in nodes:
        if iface == interface:
            return path
    # interface unknown (older kernels don't expose it) -> take the first match
    return nodes[0][0] if nodes else None


class Device:
    def __init__(self) -> None:
        path = find_hidraw()
        if path is None:
            raise RuntimeError(_NOT_FOUND)
        try:
            self._fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError as e:
            raise RuntimeError(
                f"{path}: {e}\n"
                "Install udev/70-d200x.rules, `udevadm control --reload`, then "
                "PHYSICALLY unplug/replug the deck."
            ) from e
        self.path = path
        log.info("opened %s (interface %s)", path, protocol.PROTOCOL_INTERFACE)

    def _write(self, payload: bytes) -> None:
        try:
            os.write(self._fd, payload)
        except OSError as e:
            if e.errno in _TRANSIENT:
                return
            raise DeviceGone(f"write: {e}") from e

    def read_raw(self, timeout: float = 0.0) -> bytes | None:
        try:
            r, _, _ = select.select([self._fd], [], [], timeout)
        except OSError as e:
            raise DeviceGone(f"select: {e}") from e
        if not r:
            return None
        try:
            data = os.read(self._fd, protocol.PACKET_SIZE + 1)
        except OSError as e:
            if e.errno in _TRANSIENT:
                return None
            raise DeviceGone(f"read: {e}") from e
        return bytes(data) or None

    def set_brightness(self, percent: int) -> None:
        self._write(b"\x00" + protocol.build_brightness(percent))

    def heartbeat(self) -> None:
        """Keep the deck in host mode. Send every ~2s."""
        self._write(b"\x00" + protocol.build_small_window(1, time.strftime("%H:%M:%S")))

    def send_init(self, page=None, quiet: bool = False) -> None:
        """Upload a button layout for `page` (a config.Page). Without this the
        device never reports input, and it drifts back to standalone mode unless
        repeated."""
        from .layout import build_set_buttons

        if page is None:
            payload = build_set_buttons()
        else:
            payload = build_set_buttons(
                page.labels(), page.icons(), page.icon_texts(),
                page.icon_styles(), page.style,
            )
        for pkt in protocol.frame_packets(protocol.CMD_SET_BUTTONS, payload):
            self._write(b"\x00" + pkt)
        if not quiet:
            log.info("sent SET_BUTTONS (%d-byte payload); input should now stream", len(payload))

    def poll(self) -> Iterator[protocol.InputEvent]:
        """Yield pending input events, then return."""
        while True:
            raw = self.read_raw(0.0)
            if raw is None:
                return
            ev = protocol.parse_input(raw)
            if ev is not None:
                yield ev

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass
