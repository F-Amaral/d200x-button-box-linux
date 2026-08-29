"""Map D200x input events onto the virtual gamepad / keystrokes / commands."""

from __future__ import annotations

import logging
import signal
import subprocess
import time

from . import protocol
from .config import Config
from .device import Device
from .gamepad import Gamepad
from .keyboard import KeyboardSink

log = logging.getLogger(__name__)


class Daemon:
    def __init__(self, cfg: Config, dev=None, pad=None) -> None:
        self.cfg = cfg
        self.dev = dev or Device()
        self.pad = pad or Gamepad(cfg.gamepad_buttons, cfg.gamepad_name)
        self._pulse = cfg.pulse_ms / 1000.0
        self._pending: list[tuple[float, int]] = []  # (release_at_monotonic, button)
        self._run = True

    # --- binding execution -------------------------------------------------

    def _fire(self, binding: dict, pressed: bool | None) -> None:
        """pressed True/False for a key edge; None for a discrete pulse (knob step)."""
        if not binding:
            return
        trigger = pressed is None or pressed

        if "gamepad" in binding:
            btn = int(binding["gamepad"])
            try:
                if pressed is None or binding.get("momentary"):
                    self.pad.press(btn)
                    self._pending.append((time.monotonic() + self._pulse, btn))
                elif pressed:
                    self.pad.press(btn)
                else:
                    self.pad.release(btn)
            except ValueError as ex:
                log.warning("%s (raise gamepad_buttons in the config)", ex)
        elif "key" in binding and trigger:
            self._send_key(str(binding["key"]))
        elif "command" in binding and trigger:
            subprocess.Popen(
                binding["command"], shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

    def _send_key(self, keys: str) -> None:
        for tool in (["ydotool", "key", keys], ["xdotool", "key", keys]):
            try:
                subprocess.run(tool, check=True, capture_output=True)
                return
            except FileNotFoundError:
                continue
            except subprocess.CalledProcessError as ex:
                log.warning("%s failed: %s", tool[0], ex.stderr.decode(errors="replace").strip())
                return
        log.warning("neither ydotool nor xdotool found; cannot send key %r", keys)

    # --- event routing ---------------------------------------------------

    def _on_event(self, ev: protocol.InputEvent) -> None:
        if ev.kind == "knob":
            knob = self.cfg.knobs.get(ev.index, {})
            # The encoder reports turns one-per-detent and the click only on
            # release (often bundled with the press). Fire everything as a
            # discrete pulse so a game reliably sees a button press.
            if ev.action == "release":
                return
            binding = knob.get("press" if ev.action == "press" else ev.action)
            if binding is not None:
                self._fire(binding, None)
            return

        binding = self.cfg.keys.get(ev.index)
        if binding is None:
            log.debug("unmapped key %s", ev.index)
            return
        self._fire(binding, ev.action == "press")

    def _drain_pending(self) -> None:
        if not self._pending:
            return
        now = time.monotonic()
        keep: list[tuple[float, int]] = []
        for release_at, btn in self._pending:
            if now >= release_at:
                self.pad.release(btn)
            else:
                keep.append((release_at, btn))
        self._pending = keep

    # --- main loop -----------------------------------------------------

    def run(self) -> None:
        try:
            signal.signal(signal.SIGINT, self._stop)
            signal.signal(signal.SIGTERM, self._stop)
        except ValueError:
            pass  # not the main thread (e.g. under a test harness)

        labels = {i: b["label"] for i, b in self.cfg.keys.items() if isinstance(b, dict) and b.get("label")}
        self.dev.send_init(labels)
        if self.cfg.brightness is not None:
            self.dev.set_brightness(self.cfg.brightness)

        last_beat = 0.0
        log.info("running -- ctrl-c to quit")
        with KeyboardSink(enabled=self.cfg.grab_keyboard):
            while self._run:
                for ev in self.dev.poll():
                    log.info("input: %s %s", ev.name, ev.action)
                    self._on_event(ev)
                self._drain_pending()

                now = time.monotonic()
                # Watchdog: without a periodic write the deck falls back to its
                # standalone screen and stops reporting.
                if self.cfg.heartbeat_seconds and now - last_beat > self.cfg.heartbeat_seconds:
                    self.dev.heartbeat()
                    last_beat = now

                time.sleep(0.005)

        for _, btn in self._pending:
            self.pad.release(btn)
        self.dev.close()
        self.pad.close()
        log.info("stopped")

    def _stop(self, *_) -> None:
        self._run = False
