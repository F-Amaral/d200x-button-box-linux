"""Talk to the D200x through the kernel `hidraw` node directly.

No external HID library: hidapi's PyPI wheel ships the libusb backend, which on
this hardware opens interface 0 but never delivers the interrupt-IN reports (and
throws "read error"). Reading `/dev/hidrawN` ourselves is a dozen lines and just
works. Writes prepend a 0x00 report-ID byte, as the device expects.
"""

from __future__ import annotations

import errno
import glob
import logging
import os
import re
import select
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

    def read_raw(self, timeout: float = 0.0) -> bytes | None:
        r, _, _ = select.select([self._fd], [], [], timeout)
        if not r:
            return None
        try:
            data = os.read(self._fd, protocol.PACKET_SIZE + 1)
        except OSError as e:
            if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                log.warning("hidraw read: %s", e)
            return None
        return bytes(data) or None

    def set_brightness(self, percent: int) -> None:
        try:
            os.write(self._fd, b"\x00" + protocol.build_brightness(percent))
        except OSError as e:
            log.warning("brightness write failed: %s", e)

    def heartbeat(self) -> None:
        """Keep the deck in host mode. Send every ~2s."""
        import time as _t

        try:
            os.write(self._fd, b"\x00" + protocol.build_small_window(1, _t.strftime("%H:%M:%S")))
        except OSError as e:
            log.warning("heartbeat write failed: %s", e)

    def send_init(
        self,
        labels: dict[int, str] | None = None,
        icons: dict[int, str] | None = None,
        quiet: bool = False,
    ) -> None:
        """Upload a button layout. Without this the device never reports input,
        and it drifts back to standalone mode unless this is repeated."""
        from .layout import build_set_buttons

        payload = build_set_buttons(labels, icons)
        try:
            for pkt in protocol.frame_packets(protocol.CMD_SET_BUTTONS, payload):
                os.write(self._fd, b"\x00" + pkt)
        except OSError as e:
            log.warning("SET_BUTTONS write failed: %s", e)
            return
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
