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
import hashlib
import logging
import os
import re
import select
import time
import copy
import threading
from collections import deque
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
        self._condition = threading.Condition()
        self._pending = deque()
        self._generation = 0
        self._writer = None
        self._writer_error = None
        self._closing = False
        self._active_kind = None
        log.info("opened %s (interface %s)", path, protocol.PROTOCOL_INTERFACE)

    def start_writer(self) -> None:
        """Opt in to asynchronous, serial command uploads (daemon only)."""
        if self._writer is None:
            self._writer = threading.Thread(target=self._writer_loop, name="d200x-usb", daemon=True)
            self._writer.start()

    def _check_writer(self):
        if getattr(self, "_writer_error", None):
            raise DeviceGone(str(self._writer_error))

    @property
    def layout_pending(self):
        if getattr(self, "_writer", None) is None:
            return False
        with self._condition:
            return self._active_kind == "layout" or any(job[0] == "layout" for job in self._pending)

    def _submit(self, kind, job, generation=None):
        self._check_writer()
        with self._condition:
            if self._closing:
                raise DeviceGone("USB writer is closing")
            if kind == "layout":
                self._generation += 1
                generation = self._generation
                # Latest requested page wins, but never interrupt a ZIP mid-send.
                self._pending = deque(item for item in self._pending if item[0] not in ("layout", "partial"))
            elif kind.startswith("control:"):
                self._pending = deque(item for item in self._pending if item[0] != kind)
            self._pending.append((kind, generation, job))
            self._condition.notify()

    def _writer_loop(self):
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._pending or self._closing)
                    if self._closing:
                        return
                    kind, generation, job = self._pending.popleft()
                    if kind == "partial" and generation != self._generation:
                        continue
                    self._active_kind = kind
                try:
                    job()
                except Exception as error:
                    # Publish failure before idle, so waiters cannot mistake a
                    # failed upload for a completed one.
                    with self._condition:
                        self._writer_error = error
                        self._pending.clear()
                    raise
                finally:
                    with self._condition:
                        self._active_kind = None
                        self._condition.notify_all()
        except Exception as error:
            with self._condition:
                self._writer_error = error
                self._pending.clear()
                self._condition.notify_all()
            log.exception("USB upload worker failed")
        finally:
            # The worker owns close so a blocked write cannot use a recycled fd.
            try:
                os.close(self._fd)
            except OSError:
                pass

    def wait_idle(self, timeout=5.0):
        """Wait for queued uploads; useful for diagnostics and shutdown tests."""
        if getattr(self, "_writer", None) is None:
            return
        with self._condition:
            if not self._condition.wait_for(lambda: not self._pending and self._active_kind is None,
                                           timeout=timeout):
                raise TimeoutError("USB uploads did not finish")
        self._check_writer()

    def _write(self, payload: bytes) -> None:
        if getattr(self, "_writer", None) is not None and threading.current_thread() is not self._writer:
            command = int.from_bytes(payload[3:5], "big")
            self._submit(f"control:{command}", lambda: self._write(payload))
            return
        deadline = time.monotonic() + 1.0
        while True:
            try:
                count = os.write(self._fd, payload)
                if count != len(payload):
                    raise DeviceGone(f"short HID write: {count}/{len(payload)}")
                return
            except OSError as e:
                if e.errno in _TRANSIENT and time.monotonic() < deadline:
                    time.sleep(0.001)
                    continue
                raise DeviceGone(f"write: {e}") from e

    def read_raw(self, timeout: float = 0.0) -> bytes | None:
        self._check_writer()
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
        self._brightness = int(percent)
        self._write(b"\x00" + protocol.build_brightness(percent))

    def heartbeat(self, mode: str = "clock", load: tuple[int, int, int] = (0, 0, 0)) -> None:
        """Watchdog write every ~2s.

        * ``"clock"`` — SET_SMALL_WINDOW mode 1 (the dial clock)
        * ``"load"``  — SET_SMALL_WINDOW mode 0 (CPU / RAM / GPU readout)
        * ``"off"``   — a plain SET_BRIGHTNESS re-send; the BACKGROUND mode is set
          once by :meth:`small_window_background` after each layout push, and the
          status key then shows its own icon
        """
        if mode == "load":
            pkt = protocol.build_small_window(0, "", *load)
        elif mode == "off":
            pkt = protocol.build_brightness(getattr(self, "_brightness", 80))
        else:
            pkt = protocol.build_small_window(1, time.strftime("%H:%M:%S"))
        self._write(b"\x00" + pkt)

    def small_window_background(self) -> None:
        """Put the wide status strip into BACKGROUND mode (show slot 3_2's icon)."""
        self._write(b"\x00" + protocol.build_small_window(2, time.strftime("%H:%M:%S")))

    def send_init(self, page=None, icon_cfg: dict | None = None,
                  quiet: bool = False, force: bool = False, orientation: int = 0) -> bool:
        """Upload a button layout for `page` (a config.Page). Without this the
        device never reports input, and it drifts back to standalone mode unless
        repeated.

        Skips the upload (returns False) when the rendered payload is identical
        to the last one sent — editing an action or a label that doesn't change
        any icon shouldn't blank the screens for a redundant re-push. Pass
        ``force=True`` for the periodic keep-in-host-mode re-send.
        """
        from .layout import build_set_buttons

        if getattr(self, "_writer", None) is not None and threading.current_thread() is not self._writer:
            snapshot, style = copy.deepcopy(page), copy.deepcopy(icon_cfg)
            self._submit("layout", lambda: self.send_init(snapshot, style, quiet, force, orientation))
            return True  # accepted; the worker handles payload deduplication

        started = time.perf_counter()
        payload = build_set_buttons(page, icon_cfg, orientation)
        prepared = time.perf_counter()
        h = hashlib.blake2b(payload, digest_size=16).digest()
        if not force and h == getattr(self, "_layout_hash", None):
            return False
        for pkt in protocol.frame_packets(protocol.CMD_SET_BUTTONS, payload):
            self._write(b"\x00" + pkt)
        self._layout_hash = h  # only remember a completely successful upload
        log.info("layout upload: %d bytes, prepare %.1f ms, HID writes %.1f ms",
                 len(payload), (prepared - started) * 1000,
                 (time.perf_counter() - prepared) * 1000)
        if not quiet:
            log.info("sent SET_BUTTONS (%d-byte payload); input should now stream", len(payload))
        return True

    def push_partial(self, page, indices, icon_cfg: dict | None = None,
                     orientation: int = 0) -> None:
        """Re-render just `indices` in place (no full-screen blank). Requires a
        prior :meth:`send_init`."""
        from .layout import build_set_buttons

        if getattr(self, "_writer", None) is not None and threading.current_thread() is not self._writer:
            snapshot, cells, style = copy.deepcopy(page), tuple(indices), copy.deepcopy(icon_cfg)
            self._submit("partial", lambda: self.push_partial(snapshot, cells, style, orientation),
                         generation=self._generation)
            return

        payload = build_set_buttons(page, icon_cfg, orientation, only=set(indices))
        for pkt in protocol.frame_packets(protocol.CMD_PARTIAL_UPDATE, payload):
            self._write(b"\x00" + pkt)

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
        if getattr(self, "_writer", None) is not None:
            with self._condition:
                self._closing = True
                self._pending.clear()
                self._condition.notify_all()
            self._writer.join(timeout=2.0)
            return
        try:
            os.close(self._fd)
        except OSError:
            pass
