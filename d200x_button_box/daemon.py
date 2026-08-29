"""Map D200x input events onto the virtual gamepad / keystrokes / commands.

Reloads settings + the active profile from disk on change, and switches profile
automatically when a known game process appears.
"""

from __future__ import annotations

import logging
import signal
import subprocess
import threading
import time

from . import gamedetect, protocol
from .config import ConfigStore, Profile, Settings
from .device import Device
from .gamepad import Gamepad
from .keyboard import KeyboardSink

log = logging.getLogger(__name__)

_RELOAD_POLL = 1.0   # seconds between config-file mtime checks
_DETECT_POLL = 3.0   # seconds between game-process scans


class Daemon:
    def __init__(self, store: ConfigStore | None = None, dev=None, pad=None) -> None:
        self.store = store or ConfigStore()
        s = self.store.settings
        self.dev = dev or Device()
        self.pad = pad or Gamepad(s.gamepad_buttons, s.gamepad_name)
        self._pending: list[tuple[float, int]] = []  # (release_at_monotonic, button)
        self._held: set[int] = set()                  # gamepad buttons held down right now
        self._page = 0
        self._queued_profile: str | None = None      # profile: binding, applied next tick
        self._queued_page: str | None = None         # page: binding, applied next tick
        self._home_revert_at: float | None = None     # monotonic deadline to drop back to auto
        self._run = True
        self._on_profile_change: list = []  # callbacks(name) for the API layer

    @property
    def settings(self) -> Settings:
        return self.store.settings

    @property
    def profile(self) -> Profile:
        return self.store.profile

    @property
    def page(self):
        return self.profile.page(self._page)

    @property
    def _pulse(self) -> float:
        return self.settings.pulse_ms / 1000.0

    # --- binding execution ---------------------------------------------------
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
                    self._held.add(btn)
                else:
                    self.pad.release(btn)
                    self._held.discard(btn)
            except ValueError as ex:
                log.warning("%s (raise gamepad.buttons in settings)", ex)
        elif "key" in binding and trigger:
            self._send_key(str(binding["key"]))
        elif "command" in binding and trigger:
            subprocess.Popen(
                binding["command"], shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif "profile" in binding and trigger:
            # defer: switching reloads self.profile, don't do it mid-dispatch
            self._queued_profile = str(binding["profile"])
        elif "page" in binding and trigger:
            self._queued_page = str(binding["page"])

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

    # --- event routing -----------------------------------------------------
    def _on_event(self, ev: protocol.InputEvent) -> None:
        home = self.settings.home
        if home.key is not None and ev.kind == "key" and ev.index == home.key:
            if ev.action == "press":
                self._go_home()
            return

        page = self.page
        if ev.kind == "knob":
            knob = page.knobs.get(ev.index, {})
            # Encoders report turns one-per-detent and the click only on release
            # (bundled with the press). Fire everything as a discrete pulse.
            if ev.action == "release":
                return
            binding = knob.get("press" if ev.action == "press" else ev.action)
            if binding is not None:
                self._fire(binding, None)
            return

        binding = page.keys.get(ev.index)
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

    def _release_all(self) -> None:
        """Drop every held / pending gamepad button (on page or profile change)."""
        for btn in {b for _, b in self._pending} | self._held:
            try:
                self.pad.release(btn)
            except ValueError:
                pass
        self._pending.clear()
        self._held.clear()

    # --- deck layout -----------------------------------------------------
    def push_layout(self) -> None:
        self.dev.send_init(self.page.labels(), self.page.icons(), quiet=True)

    def set_page(self, spec: str | int) -> None:
        n = self.profile.n_pages
        if n <= 1:
            return
        kw = str(spec).strip().lower()
        if kw in ("next", "+", "+1"):
            new = (self._page + 1) % n
        elif kw in ("prev", "previous", "-", "-1"):
            new = (self._page - 1) % n
        else:
            try:
                new = int(kw) % n
            except ValueError:
                log.warning("bad page spec %r", spec)
                return
        if new == self._page:
            return
        self._page = new
        self._release_all()
        self.push_layout()
        log.info("page %d/%d", self._page + 1, n)

    def set_profile(self, name: str | None) -> None:
        """Manual override from the API/CLI (None = back to auto/settings)."""
        from . import config

        if name is not None and name not in config.list_profiles():
            log.warning("profile %r does not exist; ignored", name)
            return
        self.store.force_profile(name)
        if self.store.resolve():
            self._activate()

    def _go_home(self) -> None:
        home = self.settings.home
        self.set_profile(home.profile)
        self._home_revert_at = (
            time.monotonic() + home.revert_seconds if home.revert_seconds > 0 else None
        )

    def _tick_home(self, now: float, got_input: bool) -> None:
        """In home mode: any input resets the idle timer; on expiry, drop to auto."""
        if self._home_revert_at is None:
            return
        if got_input:
            self._home_revert_at = now + self.settings.home.revert_seconds
        elif now >= self._home_revert_at:
            self._home_revert_at = None
            log.info("home idle timeout -- back to auto-detect")
            self.set_profile(None)

    def _apply_profile_binding(self, spec: str) -> None:
        """Resolve a `profile:` binding value: a name, or home / auto / next / prev."""
        from . import config

        spec = spec.strip()
        kw = spec.lower()
        if kw == "home":
            self._go_home()
            return
        self._home_revert_at = None  # any explicit choice cancels a pending auto-revert
        if kw in ("auto", "detect", "none"):
            self.set_profile(None)
            return
        if kw in ("next", "prev", "previous"):
            names = config.list_profiles()
            if not names:
                return
            try:
                i = names.index(self.store.active_name)
            except ValueError:
                i = 0
            step = 1 if kw == "next" else -1
            self.set_profile(names[(i + step) % len(names)])
            return
        self.set_profile(spec)

    def _activate(self) -> None:
        self._page = 0
        self._release_all()
        self.push_layout()
        log.info("active profile: %s (%d page(s))", self.store.active_name, self.profile.n_pages)
        for cb in self._on_profile_change:
            try:
                cb(self.store.active_name)
            except Exception:  # noqa: BLE001 - a bad callback must not kill the daemon
                log.exception("profile-change callback failed")

    # --- main loop -----------------------------------------------------
    def run(self) -> None:
        try:
            signal.signal(signal.SIGINT, self._stop)
            signal.signal(signal.SIGTERM, self._stop)
        except ValueError:
            pass  # not the main thread (test harness / embedded)

        self.dev.send_init(self.page.labels(), self.page.icons())
        if self.settings.brightness is not None:
            self.dev.set_brightness(self.settings.brightness)
        log.info("running (profile: %s) -- ctrl-c to quit", self.store.active_name)

        last_beat = last_reload = last_detect = 0.0
        detected: str | None = None

        with KeyboardSink(enabled=self.settings.grab_keyboard):
            while self._run:
                got_input = False
                for ev in self.dev.poll():
                    got_input = True
                    log.debug("input: %s %s", ev.name, ev.action)
                    self._on_event(ev)
                self._drain_pending()

                if self._queued_profile is not None:
                    self._apply_profile_binding(self._queued_profile)
                    self._queued_profile = None
                if self._queued_page is not None:
                    self.set_page(self._queued_page)
                    self._queued_page = None

                now = time.monotonic()
                self._tick_home(now, got_input)

                if now - last_detect > _DETECT_POLL:
                    detected = gamedetect.detect(self.settings.auto_detect)
                    last_detect = now
                if now - last_reload > _RELOAD_POLL:
                    if self.store.resolve(detected=detected):
                        self._activate()
                    last_reload = now
                if self.settings.heartbeat_seconds and now - last_beat > self.settings.heartbeat_seconds:
                    self.dev.heartbeat()
                    last_beat = now

                time.sleep(0.005)

        self._release_all()
        self.dev.close()
        self.pad.close()
        log.info("stopped")

    def run_in_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.run, name="d200x-daemon", daemon=True)
        t.start()
        return t

    def _stop(self, *_) -> None:
        self._run = False
