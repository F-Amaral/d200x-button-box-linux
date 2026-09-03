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

    def send_init(self, page=None, icon_cfg=None, quiet=False, force=False, orientation=0):
        self.inits.append(page)
        return True

    def push_partial(self, page, indices, icon_cfg=None, orientation=0):
        self.partials = getattr(self, "partials", [])
        self.partials.append(sorted(indices))

    def set_brightness(self, p):
        self.bright = getattr(self, "bright", [])
        self.bright.append(p)

    def heartbeat(self, mode="clock", load=(0, 0, 0)):
        self.beats = getattr(self, "beats", [])
        self.beats.append(mode)

    def small_window_background(self):
        self.bg = getattr(self, "bg", 0) + 1

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
    s.home = config.HomeConfig(profile="launcher", revert_seconds=0.05); s.nav = config.NavConfig(binds={13: {"tap": "home"}})
    d, _ = _daemon(settings=s)
    d.dev = FakeDev()

    d._on_event(InputEvent(13, "key", "press", b""))     # the home key -> queues "home"
    d._apply_profile_binding(d._queued_profile); d._queued_profile = None
    assert d.store.active_name == "launcher"
    assert d._home_revert_at is not None

    d._tick_home(time.monotonic(), got_input=True)       # activity keeps it in home
    assert d._home_revert_at is not None
    time.sleep(0.06)
    d._tick_home(time.monotonic(), got_input=False)      # idle past deadline -> revert
    assert d._home_revert_at is None
    assert d.store._forced_profile is None


def test_explicit_binding_wins_over_home_key():
    s = config.Settings(pulse_ms=10)
    s.home = config.HomeConfig(profile="x", revert_seconds=0); s.nav = config.NavConfig(binds={13: {"tap": "home"}})
    d, pad = _daemon(keys={13: {"gamepad": 5}}, settings=s)
    d._on_event(InputEvent(13, "key", "press", b""))
    assert pad.events == [("press", 5)]  # the explicit binding, not home


def test_home_synthesised_when_no_explicit_binding(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path)
    for n in ("default", "launcher"):
        config.save_profile(config.default_profile(n))
    s = config.Settings(pulse_ms=10)
    s.home = config.HomeConfig(profile="launcher", revert_seconds=0)
    s.nav = config.NavConfig(binds={7: {"tap": "home"}})
    d, _ = _daemon(settings=s)
    d.dev = FakeDev()
    d._on_event(InputEvent(7, "key", "press", b""))
    d._apply_profile_binding(d._queued_profile); d._queued_profile = None
    assert d.store.active_name == "launcher"


def test_aux_hold_is_home_when_multipage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path)
    for n in ("t", "launcher"):
        config.save_profile(config.default_profile(n))
    s = config.Settings(pulse_ms=10, hold_ms=50)
    s.home = config.HomeConfig(profile="launcher", revert_seconds=0)
    s.nav = config.NavConfig(binds={15: {"tap": "prev_page", "hold": "home"}, 16: {"tap": "next_page"}})
    d, _ = _daemon(pages=[config.Page(name="a"), config.Page(name="b")], settings=s)
    d.dev = FakeDev()

    # a quick tap -> page prev, not home
    d._on_event(InputEvent(15, "key", "press", b""))
    d._on_event(InputEvent(15, "key", "release", b""))
    assert d._queued_page == "prev" and d._queued_profile is None
    d._queued_page = None

    # held past the threshold -> home
    d._on_event(InputEvent(15, "key", "press", b""))
    assert 15 in d._pressed
    time.sleep(0.06)
    d._tick_hold(time.monotonic())
    assert d._queued_profile == "home"
    d._apply_profile_binding("home")
    assert d.store.active_name == "launcher"


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


def test_sync_game_labels_fills_only_blanks(monkeypatch):
    from d200x_button_box import config as cfgmod
    from d200x_button_box import gamedetect, games

    pages = [config.Page(keys={
        0: {"gamepad": 1},                       # blank -> gets labeled
        1: {"gamepad": 2, "label": "My Name"},   # kept
        2: {"gamepad": 3},                       # game doesn't bind it -> stays blank
    })]
    d, _ = _daemon(pages=pages, settings=config.Settings(games={"lmu": "/x"}))
    d.store.profile.game = "lmu"

    monkeypatch.setattr(games, "detect_hints", lambda: {"lmu": ["LeMansUltimate"]})
    monkeypatch.setattr(gamedetect, "detect", lambda ad: "lmu")
    monkeypatch.setattr(games, "read", lambda g, p: {1: ["Headlights"], 2: ["Wipers"]})
    saved = []
    monkeypatch.setattr(cfgmod, "save_profile", lambda prof: saved.append(prof))

    d._sync_game_labels()
    assert d.store.profile.pages[0].keys[0]["label"] == "Headlights"
    assert d.store.profile.pages[0].keys[1]["label"] == "My Name"
    assert "label" not in d.store.profile.pages[0].keys[2]
    assert len(saved) == 1

    d._sync_game_labels()                        # converged -> no second save
    assert len(saved) == 1


def test_sync_game_labels_skips_placeholders_and_feeds_learn(monkeypatch):
    from d200x_button_box import config as cfgmod
    from d200x_button_box import gamedetect, games
    from d200x_button_box.games import Game

    pages = [config.Page(keys={
        0: {"gamepad": 1, "label": "Cockpit Cam"},   # a name the user typed
        1: {"gamepad": 2},                            # game returns "control 9" -> stays blank
    })]
    d, _ = _daemon(pages=pages, settings=config.Settings(games={"ac_evo": "/x"}))
    d.store.profile.game = "ac_evo"

    monkeypatch.setattr(games, "detect_hints", lambda: {"ac_evo": ["acevo"]})
    monkeypatch.setattr(gamedetect, "detect", lambda ad: "ac_evo")
    monkeypatch.setattr(games, "read", lambda g, p: {1: ["control 415"], 2: ["control 9"]})
    monkeypatch.setattr(cfgmod, "save_profile", lambda prof: None)
    learned = []
    monkeypatch.setitem(games.ALL, "ac_evo",
                        Game(key="ac_evo", label="AC EVO", read=lambda p: {},
                             learn=lambda path, labels: learned.append(labels)))

    d._sync_game_labels()
    assert "label" not in d.store.profile.pages[0].keys[1]   # "control 9" is a placeholder, not a label
    assert learned == [{1: "Cockpit Cam"}]                   # your label fed to learn()


def test_sync_game_labels_noop_when_game_not_running(monkeypatch):
    from d200x_button_box import gamedetect, games

    d, _ = _daemon(pages=[config.Page(keys={0: {"gamepad": 1}})],
                   settings=config.Settings(games={"lmu": "/x"}))
    d.store.profile.game = "lmu"
    monkeypatch.setattr(games, "detect_hints", lambda: {"lmu": ["LeMansUltimate"]})
    monkeypatch.setattr(gamedetect, "detect", lambda ad: None)   # not running
    monkeypatch.setattr(games, "read", lambda g, p: (_ for _ in ()).throw(AssertionError("read called")))
    d._sync_game_labels()
    assert "label" not in d.store.profile.pages[0].keys[0]


def test_orientation_180_remaps_input_index():
    # logical profile: key 0 holds button 1, key 12 holds button 13
    d, pad = _daemon(pages=[config.Page(keys={0: {"gamepad": 1}, 12: {"gamepad": 13}})],
                     settings=config.Settings(pulse_ms=10, orientation=180))
    d.dev = FakeDev()
    # firmware reports *physical* key 12 -> should hit logical key 0 -> button 1
    d._on_event(InputEvent(12, "key", "press", b""))
    assert ("press", 1) in pad.events
    # physical key 0 -> logical key 12 -> button 13
    d._on_event(InputEvent(0, "key", "press", b""))
    assert ("press", 13) in pad.events


def test_widget_tick_pushes_only_changed_cells(monkeypatch):
    from d200x_button_box import layout, widgets

    sk = config.protocol.STATUS_KEY_INDEX
    d, _ = _daemon(pages=[config.Page(keys={
        sk: {"widget": "clock"},
        3: {"widget": "sysload"},
    })])
    d.dev = FakeDev()

    renders = {sk: iter(["A", "A", "B"]), 3: iter(["x", "y", "z"])}
    monkeypatch.setattr(layout, "render_cell",
                        lambda page, idx, cfg, rot: next(renders[idx]).encode())
    monkeypatch.setattr(widgets, "interval", lambda b: 0.0)   # always due

    d._tick_widgets(100.0)   # baseline A / x already primed? no -> both dirty
    d._tick_widgets(200.0)   # A unchanged, y changed -> only cell 3
    d._tick_widgets(300.0)   # B and z changed -> both

    assert d.dev.partials == [[3, sk], [3], [3, sk]]


def test_status_mode_widget_disables_firmware_overlay():
    sk = config.protocol.STATUS_KEY_INDEX
    d, _ = _daemon(pages=[config.Page(keys={sk: {"widget": "clock"}})])
    assert d._status_mode() == "off"   # so push_layout sets BACKGROUND mode


def test_idle_sleep_and_wake():
    d, _ = _daemon(pages=[config.Page(keys={0: {"gamepad": 1}})],
                   settings=config.Settings(pulse_ms=10, idle_sleep_seconds=60, brightness=70))
    d.dev = FakeDev()

    d._sleep()
    assert d._asleep and d.dev.bright[-1] == 0
    d._sleep()                              # idempotent
    assert d.dev.bright == [0]

    d._wake()
    assert not d._asleep and d.dev.bright[-1] == 70
    assert d.dev.inits                      # re-pushed the layout on wake
    d._wake()                               # idempotent
    assert d.dev.bright == [0, 70]


def test_wake_press_is_swallowed():
    events = [InputEvent(0, "key", "press", b"")]
    d, pad = _daemon(pages=[config.Page(keys={0: {"gamepad": 1}})],
                     settings=config.Settings(pulse_ms=10, idle_sleep_seconds=60))
    d.dev = FakeDev()
    d._asleep = True
    # emulate the loop: asleep + input -> wake, skip dispatch
    if d._asleep:
        d._wake()
    else:
        for ev in events:
            d._on_event(ev)
    assert ("press", 1) not in pad.events


def test_sysload_and_status_mode():
    sk = config.protocol.STATUS_KEY_INDEX
    d, _ = _daemon(pages=[config.Page(keys={sk: {"status": "load"}})])
    d.dev = FakeDev()

    d._sysload()                       # prime the cpu delta
    a, b, g = d._sysload()
    assert 0 <= a <= 100 and 0 <= b <= 100 and g == 0

    assert d._status_mode() == "load"
    d.page.keys[sk] = {"clock": False}
    assert d._status_mode() == "load"          # legacy `clock: false`
    d.page.keys[sk] = {"status": "off"}
    assert d._status_mode() == "off"
    d.page.keys[sk] = {}
    assert d._status_mode() == "clock"         # default
