"""Settings + per-game profiles.

Layout on disk (``~/.config/d200x-button-box/``)::

    settings.yaml            device / gamepad / api / active profile / auto-detect
    profiles/<name>.yaml     keys + knobs bindings for one game

A *binding* is a dict with exactly one of ``gamepad`` / ``key`` / ``command``,
plus optional ``label`` and ``icon`` (path to an image) for the LCD key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import protocol

# D200X_CONFIG_DIR overrides the location (handy for tests / throwaway configs).
CONFIG_DIR = Path(os.environ.get("D200X_CONFIG_DIR") or (Path.home() / ".config" / "d200x-button-box"))
SETTINGS_PATH = CONFIG_DIR / "settings.yaml"
PROFILES_DIR = CONFIG_DIR / "profiles"

# every physical control, in a stable order (used by the default profile + GUI)
KEY_INDICES = [*range(13), protocol.STATUS_KEY_INDEX, *protocol.PAGE_KEY_INDICES]
KNOB_INDICES = list(protocol.KNOB_INDICES)


# --------------------------------------------------------------------------- #
#  Settings
# --------------------------------------------------------------------------- #
@dataclass
class ApiConfig:
    host: str = "127.0.0.1"          # 0.0.0.0 to reach it from the LAN (phone)
    port: int = 8377
    token: str | None = None         # require ?token= / X-Token when set


@dataclass
class HomeConfig:
    """A 'go home' control that works in every profile."""
    key: int | None = None           # control index; None = feature off
    profile: str = "launcher"        # where the home key jumps to
    revert_seconds: float = 5        # idle seconds before returning to auto-detect; 0 = stay


@dataclass
class Settings:
    brightness: int | None = 80
    heartbeat_seconds: float = 2
    grab_keyboard: bool = True
    gamepad_name: str = "D200x Button Box"
    gamepad_buttons: int = 32
    pulse_ms: int = 60
    active_profile: str = "default"
    auto_detect: dict[str, list[str]] = field(default_factory=dict)
    games: dict[str, str] = field(default_factory=dict)  # game -> install path (for label import)
    home: HomeConfig = field(default_factory=HomeConfig)
    api: ApiConfig = field(default_factory=ApiConfig)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Settings":
        path = Path(path or SETTINGS_PATH)
        raw = (yaml.safe_load(path.read_text()) if path.exists() else {}) or {}
        return cls.from_raw(raw)

    @classmethod
    def from_raw(cls, raw: dict) -> "Settings":
        raw = raw or {}
        dev = raw.get("device", {}) or {}
        pad = raw.get("gamepad", {}) or {}
        api = raw.get("api", {}) or {}
        home = raw.get("home", {}) or {}
        return cls(
            brightness=dev.get("brightness", cls.brightness),
            heartbeat_seconds=float(dev.get("heartbeat_seconds", cls.heartbeat_seconds)),
            grab_keyboard=bool(dev.get("grab_keyboard", cls.grab_keyboard)),
            gamepad_name=pad.get("name", cls.gamepad_name),
            gamepad_buttons=int(pad.get("buttons", cls.gamepad_buttons)),
            pulse_ms=int(raw.get("pulse_ms", cls.pulse_ms)),
            active_profile=raw.get("active_profile", cls.active_profile),
            auto_detect={k: list(v) for k, v in (raw.get("auto_detect") or {}).items()},
            games={k: str(v) for k, v in (raw.get("games") or {}).items()},
            home=HomeConfig(
                key=home.get("key"),
                profile=home.get("profile", "launcher"),
                revert_seconds=float(home.get("revert_seconds", 5)),
            ),
            api=ApiConfig(
                host=api.get("host", "127.0.0.1"),
                port=int(api.get("port", 8377)),
                token=api.get("token"),
            ),
        )

    def to_dict(self) -> dict:
        return {
            "device": {
                "brightness": self.brightness,
                "heartbeat_seconds": self.heartbeat_seconds,
                "grab_keyboard": self.grab_keyboard,
            },
            "gamepad": {"name": self.gamepad_name, "buttons": self.gamepad_buttons},
            "pulse_ms": self.pulse_ms,
            "active_profile": self.active_profile,
            "auto_detect": self.auto_detect,
            "games": self.games,
            "home": {
                "key": self.home.key,
                "profile": self.home.profile,
                "revert_seconds": self.home.revert_seconds,
            },
            "api": {"host": self.api.host, "port": self.api.port, "token": self.api.token},
        }

    def save(self, path: Path | str | None = None) -> None:
        path = Path(path or SETTINGS_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(self.to_dict(), sort_keys=False))


# --------------------------------------------------------------------------- #
#  Profiles (each is one or more pages of bindings)
# --------------------------------------------------------------------------- #
@dataclass
class Page:
    name: str = ""
    keys: dict[int, dict] = field(default_factory=dict)   # index -> binding
    knobs: dict[int, dict] = field(default_factory=dict)  # index -> {left/right/press: binding}
    style: dict = field(default_factory=dict)             # default generated-icon style for this page

    def _pick(self, field_name: str) -> dict:
        return {i: b[field_name] for i, b in self.keys.items()
                if isinstance(b, dict) and b.get(field_name)}

    def labels(self) -> dict[int, str]:
        return self._pick("label")

    def icons(self) -> dict[int, str]:
        return self._pick("icon")

    def icon_texts(self) -> dict[int, str]:
        return self._pick("icon_text")

    def icon_styles(self) -> dict[int, dict]:
        return self._pick("icon_style")

    def icon_paths_in_use(self) -> set[str]:
        return set(self.icons().values())

    def to_dict(self) -> dict:
        d: dict = {}
        if self.name:
            d["name"] = self.name
        if self.style:
            d["style"] = self.style
        d["keys"] = {i: self.keys[i] for i in sorted(self.keys)}
        d["knobs"] = {i: self.knobs[i] for i in sorted(self.knobs)}
        return d


@dataclass
class Profile:
    name: str = "default"
    pages: list[Page] = field(default_factory=lambda: [Page()])

    def page(self, i: int) -> Page:
        return self.pages[i % len(self.pages)] if self.pages else Page()

    @property
    def n_pages(self) -> int:
        return len(self.pages)

    def to_dict(self) -> dict:
        if len(self.pages) == 1 and not self.pages[0].name:
            return self.pages[0].to_dict()  # keep single-page profiles flat
        return {"pages": [p.to_dict() for p in self.pages]}


def profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{_safe_name(name)}.yaml"


def list_profiles() -> list[str]:
    if not PROFILES_DIR.is_dir():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))


def _page_from_dict(raw: dict) -> Page:
    page = Page(name=raw.get("name", ""), style=dict(raw.get("style") or {}))
    for k, v in (raw.get("keys") or {}).items():
        page.keys[int(k)] = v or {}
    for k, v in (raw.get("knobs") or {}).items():
        page.knobs[int(k)] = v or {}
    return page


def profile_from_raw(name: str, raw: dict) -> Profile:
    raw = raw or {}
    if raw.get("pages"):
        pages = [_page_from_dict(p or {}) for p in raw["pages"]]
    else:
        pages = [_page_from_dict(raw)]  # flat keys+knobs = single page
    return Profile(name=name, pages=pages or [Page()])


def load_profile(name: str) -> Profile:
    path = profile_path(name)
    raw = (yaml.safe_load(path.read_text()) if path.exists() else {}) or {}
    return profile_from_raw(name, raw)


def write_settings_dict(raw: dict) -> None:
    """Validate a settings dict by round-tripping through the dataclass, then save."""
    Settings.from_raw(raw).save()


def write_profile_dict(name: str, raw: dict) -> None:
    save_profile(profile_from_raw(name, raw))


def delete_profile(name: str) -> bool:
    path = profile_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


def gc_icons() -> int:
    """Delete uploaded icons in CONFIG_DIR/icons/ that no profile references."""
    icons_dir = CONFIG_DIR / "icons"
    if not icons_dir.is_dir():
        return 0
    used: set[str] = set()
    for name in list_profiles():
        for page in load_profile(name).pages:
            used |= {Path(p).name for p in page.icon_paths_in_use()}
    removed = 0
    for f in icons_dir.glob("*.png"):
        if f.name not in used:
            f.unlink()
            removed += 1
    return removed


def save_profile(prof: Profile) -> None:
    path = profile_path(prof.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(prof.to_dict(), sort_keys=False, allow_unicode=True))


HOME_KEY_INDEX = protocol.PAGE_KEY_INDICES[0]  # leftmost aux button (no screen) = go home


def default_profile(name: str = "default") -> Profile:
    """One page, with a STABLE control -> gamepad-button map so restructuring
    never shifts existing in-game bindings:

        LCD key i (0..12)  -> button i + 1        (1..13)
        wide status key    -> button 14
        aux L / aux R      -> home / page  (buttons 15, 16 reserved, unused)
        encoder 17 L/R/click -> buttons 17, 18, 19
        encoder 18           -> 20, 21, 22
        encoder 19           -> 23, 24, 25

    The leftmost aux button is the global home key (settings.home); the right
    one cycles pages.
    """
    page = Page()
    for i in KEY_INDICES:
        if i == HOME_KEY_INDEX:
            page.keys[i] = {"profile": "home"}
        elif i == protocol.PAGE_KEY_INDICES[1]:
            page.keys[i] = {"page": "next"}
        else:
            label = "STATUS" if i == protocol.STATUS_KEY_INDEX else f"BTN {i + 1}"
            page.keys[i] = {"gamepad": i + 1, "label": label}
    for pos, i in enumerate(KNOB_INDICES):
        base = 17 + pos * 3
        page.knobs[i] = {
            "left": {"gamepad": base},
            "right": {"gamepad": base + 1},
            "press": {"gamepad": base + 2},
        }
    return Profile(name=name, pages=[page])


# --------------------------------------------------------------------------- #
#  Live store: settings + resolved active profile, reloaded on file changes
# --------------------------------------------------------------------------- #
class ConfigStore:
    """Holds the current Settings + active Profile and reloads them on disk change."""

    def __init__(self, settings_path: Path | None = None) -> None:
        self.settings_path = Path(settings_path or SETTINGS_PATH)
        self.settings = Settings.load(self.settings_path)
        self._forced_profile: str | None = None  # manual override (API / CLI)
        self._active_name = ""
        self.profile = Profile()
        self._mtimes: dict[Path, float] = {}
        self.resolve(force_reload=True)

    # -- profile resolution ------------------------------------------------
    def _target_profile_name(self, detected: str | None) -> str:
        if self._forced_profile:
            return self._forced_profile
        if detected:
            return detected
        return self.settings.active_profile or "default"

    def resolve(self, detected: str | None = None, force_reload: bool = False) -> bool:
        """Reload settings/profile if files or the target profile changed.

        Returns True if the active profile's content changed (caller re-pushes
        the deck layout).
        """
        changed = force_reload
        if self._file_changed(self.settings_path):
            self.settings = Settings.load(self.settings_path)
            changed = True

        name = self._target_profile_name(detected)
        path = profile_path(name)
        # evaluate _file_changed unconditionally so it primes the mtime cache
        file_changed = self._file_changed(path)
        if force_reload or file_changed or name != self._active_name:
            self.profile = load_profile(name)
            self._active_name = name
            changed = True
        return changed

    def force_profile(self, name: str | None) -> None:
        self._forced_profile = name

    @property
    def active_name(self) -> str:
        return self._active_name

    def _file_changed(self, path: Path) -> bool:
        mtime = path.stat().st_mtime if path.exists() else 0.0
        if self._mtimes.get(path) != mtime:
            self._mtimes[path] = mtime
            return True
        return False


def _safe_name(name: str) -> str:
    keep = "".join(c for c in name if c.isalnum() or c in "-_")
    return keep or "profile"


BUILTIN_PROFILE_ORDER = ["default", "lmu", "ac_evo"]

# "launcher" is active when no game is running: start things and jump to a game
# profile from the deck itself. Written verbatim so the examples keep comments.
LAUNCHER_TEMPLATE = """\
# launcher profile -- active when no game is detected (it is the `active_profile`
# in settings.yaml). Bindings: command / profile / gamepad / key.
#   profile: lmu        switch to that profile
#   profile: auto       back to auto-detect / active_profile
#   profile: next|prev  cycle profiles
keys:
  0:
    label: "LMU + VR"
    command: "steam steam://rungameid/2399420"
  1:
    label: "CrewChief"
    command: "sh -c 'cd ~/CrewChiefV4 && ./CrewChief.sh &'"
  2:
    label: "-> LMU"
    profile: "lmu"
  3:
    label: "-> AC EVO"
    profile: "ac_evo"
  4:
    label: "Auto"
    profile: "auto"
knobs: {}
"""


def bootstrap() -> None:
    """Create the config dir with a settings file and starter profiles if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        s = Settings()
        s.active_profile = "launcher"
        s.auto_detect = {"lmu": ["LeMansUltimate"], "ac_evo": ["AssettoCorsaEVO", "acevo"]}
        s.home = HomeConfig(key=HOME_KEY_INDEX, profile="launcher", revert_seconds=5)
        try:
            from .gameimport import find_lmu

            if (lmu := find_lmu()):
                s.games["lmu"] = lmu
        except Exception:  # noqa: BLE001
            pass
        s.save()
    if not list_profiles():
        for name in BUILTIN_PROFILE_ORDER:
            save_profile(default_profile(name))
        profile_path("launcher").write_text(LAUNCHER_TEMPLATE)
