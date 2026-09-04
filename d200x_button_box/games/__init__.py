"""Per-game support: config discovery, import (read), and bind-to-game (write).

Each supported simulator is a `Game` defined in `games/<key>.py` and collected in
`ALL`. The rest of the app talks only to this module (`available`, `read`,
`controls`, `bind`, `detect_hints`) -- never to a game module directly.

Adding a sim = one new `games/<key>.py` ending in `GAME = Game(...)`, plus its
import here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


def _nothing() -> None:
    return None


@dataclass(frozen=True)
class Game:
    key: str                                   # stable id, also the default profile name
    label: str                                 # display name ("AC Rally")
    detect: tuple[str, ...] = ()               # process-name substrings (auto_detect seed)
    find: Callable[[], Optional[str]] = _nothing    # locate config/install, or None
    read: Optional[Callable[..., dict]] = None      # import -> {button (1-based): [control names]}
    controls: Optional[Callable[..., dict]] = None  # bindable list + which are bound to the deck
    write: Optional[Callable[..., dict]] = None     # bind-to-game: point a control at a button
    learn: Optional[Callable[..., None]] = None     # (path, {button: deck label}) -> remember names


from .lmu import GAME as _lmu           # noqa: E402
from .ac import GAME as _ac              # noqa: E402
from .ac_rally import GAME as _ac_rally  # noqa: E402
from .ac_evo import GAME as _ac_evo      # noqa: E402

ALL: dict[str, Game] = {g.key: g for g in (_lmu, _ac, _ac_rally, _ac_evo)}


def get(key: str) -> Optional[Game]:
    return ALL.get(key)


def _require(key: str) -> Game:
    g = ALL.get(key)
    if g is None:
        raise ValueError(f"unknown game {key!r}")
    return g


def detect_hints() -> dict[str, list[str]]:
    """{game key -> process-name substrings}, to seed settings.auto_detect."""
    return {k: list(g.detect) for k, g in ALL.items() if g.detect}


def available() -> dict[str, dict]:
    """{key -> {path, label, can_read, can_write}} for every known game."""
    return {
        k: {
            "path": g.find(),
            "label": g.label,
            "can_read": g.read is not None,
            "can_write": g.write is not None,
        }
        for k, g in ALL.items()
    }


def read(key: str, path) -> dict[int, list[str]]:
    g = _require(key)
    if g.read is None:
        raise ValueError(f"no importer for {key!r}")
    return g.read(path)


def controls(key: str, path) -> dict:
    g = _require(key)
    if g.controls is None:
        raise ValueError(f"cannot list controls for {key!r}")
    return g.controls(path)


def bind(key: str, path, control: str, button: int | None) -> dict:
    g = _require(key)
    if g.write is None:
        raise ValueError(f"cannot write bindings for {key!r}")
    return g.write(path, control, button)
