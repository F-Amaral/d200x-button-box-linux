"""Guess which game is running by scanning process command lines.

`auto_detect` in settings maps a profile name to a list of case-insensitive
substrings; the first profile whose substrings appear in any running command
line wins. Falls back to matching a game's Steam install / prefix path (from
`settings.games`) so a bad hint doesn't make the daemon think nothing is
running. Cheap enough to call every few seconds.
"""

from __future__ import annotations

import glob
import re


def _cmdlines() -> list[str]:
    out = []
    for path in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(path, "rb") as f:
                out.append(f.read().replace(b"\x00", b" ").decode("utf-8", "replace").lower())
        except OSError:
            continue
    return out


def _path_fragments(game_paths: dict[str, str] | None):
    """(game key, a distinctive lowercased path fragment) from settings.games —
    the Steam library folder or the `compatdata/<appid>` dir, either of which
    shows up in a Proton/Wine game's command line."""
    for key, path in (game_paths or {}).items():
        m = re.search(r"steamapps/common/[^/]+|compatdata/\d+", str(path or ""))
        if m:
            yield key, m.group(0).lower()


def detect(auto_detect: dict[str, list[str]] | None = None,
           game_paths: dict[str, str] | None = None) -> str | None:
    if not auto_detect and not game_paths:
        return None
    cmds = _cmdlines()
    for profile, needles in (auto_detect or {}).items():
        for needle in needles:
            n = (needle or "").lower()
            if n and any(n in cmd for cmd in cmds):
                return profile
    for key, frag in _path_fragments(game_paths):
        if any(frag in cmd for cmd in cmds):
            return key
    return None
