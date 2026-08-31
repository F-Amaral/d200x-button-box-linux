"""Event routing + profile switching, with fakes for the device and gamepad."""

import time

from d200x_button_box import config
from d200x_button_box.daemon import Daemon
from d200x_button_box.protocol import InputEvent


class FakePad:
    def __init__(self):
        self.events = []

    def press(self, b):
        self.events.append(("press", b))

    def release(self, b):
        self.events.append(("release", b))

    def close(self):
        pass


class FakeDev:
    def __init__(self):
        self.inits = []

    def send_init(self, page=None, quiet=False):
        self.inits.append(page)

    def set_brightness(self, p):
        pass

    def heartbeat(self):
        pass

    def poll(self):
        return iter(())

    def close(self):
        pass


def _daemon(keys=None, knobs=None, pages=None, settings=None,
            settings_path="/nonexistent/settings.yaml"):
    from pathlib import Path

    store = config.ConfigStore.__new__(config.ConfigStore)
    store.settings_path = Path(settings_path)
    store.settings = settings or config.Settings(pulse_ms=10)
    store.profile = config.Profile(
        name="t",
        pages=pages or [config.Page(keys=keys or {}, knobs=knobs or {})],
    )
    store._forced_profile = None
    store._active_name = "t"
    # prime the mtime cache like the real __init__ does, so resolve() does not
    # reload (and clobber) settings from a path that does not exist
    store._mtimes = {store.settings_path: 0.0}
    d = Daemon(store, dev=FakeDev(), pad=FakePad())
    return d, d.pad


def test_key_press_release_maps_to_hold():
    d, pad = _daemon(keys={3: {"gamepad": 7}})
    d._on_event(InputEvent(3, "key", "press", b""))
    d._on_event(InputEvent(3, "key", "release", b""))
    assert pad.events == [("press", 7), ("release", 7)]


def test_unmapped_key_ignored():
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


def test_knob_turn_pulses():
    d, pad = _daemon(knobs={17: {"left": {"gamepad": 15}, "right": {"gamepad": 16}}})
    d._on_event(InputEvent(17, "knob", "right", b""))
    assert pad.events == [("press", 16)]
    time.sleep(0.02)
    d._drain_pending()
    assert pad.events[-1] == ("release", 16)


def test_knob_click_pulses_and_ignores_release():
    d, pad = _daemon(knobs={18: {"press": {"gamepad": 20}}})
    d._on_event(InputEvent(18, "knob", "press", b""))
    d._on_event(InputEvent(18, "knob", "release", b""))
    assert pad.events == [("press", 20)]


def test_out_of_range_button_does_not_crash():
    d, pad = _daemon(keys={0: {"gamepad": 999}})

    def boom(_):
        raise ValueError("out of range")

    d.pad.press = boom
    d._on_event(InputEvent(0, "key", "press", b""))  # logged, not raised


def test_profile_switch_repushes_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path)
    config.save_profile(config.default_profile("default"))
    lmu = config.default_profile("lmu")
    lmu.page(0).keys[0]["label"] = "PIT"
    config.save_profile(lmu)

    d, _ = _daemon()
    d.dev = FakeDev()
    d.set_profile("lmu")
    assert d.store.active_name == "lmu"
    assert d.dev.inits and d.dev.inits[-1].labels().get(0) == "PIT"

    d.set_profile("nope")            # missing -> ignored, stays on lmu
    assert d.store.active_name == "lmu"


def test_profile_binding_queues_and_cycles(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path)
    for n in ("default", "lmu", "launcher"):
        config.save_profile(config.default_profile(n))

    d, _ = _daemon(keys={0: {"profile": "lmu"}, 1: {"profile": "next"}, 2: {"profile": "auto"}})
    d.dev = FakeDev()

    d._on_event(InputEvent(0, "key", "press", b""))
    assert d._queued_profile == "lmu"
    d._apply_profile_binding(d._queued_profile); d._queued_profile = None
    assert d.store.active_name == "lmu"

    d._apply_profile_binding("next")     # sorted [default, launcher, lmu]; lmu -> wraps to default
    assert d.store.active_name == "default"

    d._apply_profile_binding("auto")     # clears the override
    assert d.store._forced_profile is None


def test_home_key_switches_and_reverts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path)
    for n in ("default", "launcher", "lmu"):
        config.save_profile(config.default_profile(n))

    s = config.Settings(pulse_ms=10)
    s.home = config.HomeConfig(key=13, profile="launcher", revert_seconds=0.05)
    d, _ = _daemon(settings=s)
    d.dev = FakeDev()

    d._on_event(InputEvent(13, "key", "press", b""))     # the home key
    assert d.store.active_name == "launcher"
    assert d._home_revert_at is not None

    d._tick_home(time.monotonic(), got_input=True)       # activity keeps it in home
    assert d._home_revert_at is not None
    time.sleep(0.06)
    d._tick_home(time.monotonic(), got_input=False)      # idle past deadline -> revert
    assert d._home_revert_at is None
    assert d.store._forced_profile is None


def test_home_key_press_is_not_forwarded_as_binding():
    s = config.Settings(pulse_ms=10)
    s.home = config.HomeConfig(key=13, profile="x", revert_seconds=0)
    d, pad = _daemon(keys={13: {"gamepad": 5}}, settings=s)
    d._on_event(InputEvent(13, "key", "press", b""))
    assert pad.events == []  # intercepted, not sent to the gamepad


def test_pages_cycle_and_repush(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path)
    pages = [
        config.Page(name="a", keys={0: {"gamepad": 1, "label": "A"}, 12: {"page": "next"}}),
        config.Page(name="b", keys={0: {"gamepad": 2, "label": "B"}}),
    ]
    d, pad = _daemon(pages=pages)
    d.dev = FakeDev()

    assert d.page.name == "a"
    d._on_event(InputEvent(0, "key", "press", b""))
    assert pad.events == [("press", 1)]        # page a -> button 1

    d.set_page("next")
    assert d.page.name == "b"
    assert d.dev.inits[-1].labels() == {0: "B"}      # re-pushed page b
    d._on_event(InputEvent(0, "key", "press", b""))
    assert pad.events[-1] == ("press", 2)      # page b -> button 2

    d.set_page("next")                          # wraps back to a
    assert d.page.name == "a"


def test_starts_without_a_device_and_reconnects(monkeypatch):
    from d200x_button_box import daemon as dmod

    d, _ = _daemon()
    d.dev = None  # no device at startup

    attempts = {"n": 0}

    class FlakyDevice(FakeDev):
        def __init__(self):
            super().__init__()
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("not found")
            self.path = "/dev/hidraw9"

    monkeypatch.setattr(dmod, "Device", FlakyDevice)
    d._kbd.enabled = False  # don't touch real evdev in tests

    assert d._connect_device() is False and d.dev is None
    assert d._connect_device() is True and d.dev is not None
    assert d.snapshot()["device"]["connected"] is True

    d._disconnect_device("test")
    assert d.dev is None and d.snapshot()["device"]["connected"] is False


def test_device_gone_during_layout_push_disconnects(monkeypatch):
    from d200x_button_box.device import DeviceGone

    d, _ = _daemon()
    d._kbd.enabled = False

    class DyingDev(FakeDev):
        def send_init(self, *a, **k):
            raise DeviceGone("write: ENODEV")

    d.dev = DyingDev()
    d.push_layout()
    assert d.dev is None  # push_layout caught DeviceGone and disconnected


def test_page_switch_releases_held_button():
    pages = [
        config.Page(keys={0: {"gamepad": 1}}),
        config.Page(keys={0: {"gamepad": 9}}),
    ]
    d, pad = _daemon(pages=pages)
    d.dev = FakeDev()
    d._on_event(InputEvent(0, "key", "press", b""))   # holds button 1
    assert ("press", 1) in pad.events
    d.set_page("next")
    assert ("release", 1) in pad.events               # released on page change
