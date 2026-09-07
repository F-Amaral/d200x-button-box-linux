"""Guess which game is running by scanning process command lines.

`auto_detect` in settings maps a profile name to a list of case-insensitive
substrings; a match counts only when the substring sits right next to a launched
``.exe`` in some process's command line -- a real game invocation, not the
folder path lingering in a shader-cache / overlay / wineserver / file-manager
command line long after the game closed. Falls back to matching a game's Steam
install / prefix path (from `settings.games`) the same way.

When more than one game matches (the old one is still tearing down while the new
one starts), the one whose process started **most recently** wins, so
close-A-then-open-B switches cleanly instead of sticking on A.

ponytail: no debounce -- youngest-process + path-adjacent-.exe already kills the
stuck-on-a-closed-game case. Add an N-scan confirm only if launch-time flap
(a blip through the launcher profile while a game loads) actually annoys.
"""

from __future__ import annotations

import glob
import re


def _procs() -> list[tuple[str, float]]:
    """[(lowercased command line, start-time in clock ticks)] for every readable
    process. Start time is comparable between processes (same units, same boot);
    0.0 when it can't be read."""
    out: list[tuple[str, float]] = []
    for cmdline_path in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(cmdline_path, "rb") as f:
                cmd = f.read().replace(b"\x00", b" ").decode("utf-8", "replace").lower()
        except OSError:
            continue
        if not cmd.strip():
            continue
        start = 0.0
        try:
            with open(cmdline_path[:-7] + "stat", "rb") as f:   # /proc/<pid>/stat
                stat = f.read()
            # fields after the last ")" : state ppid ... starttime(22nd overall)
            start = float(stat[stat.rfind(b")") + 2:].split()[19])
        except (OSError, ValueError, IndexError):
            pass
        out.append((cmd, start))
    return out


def _path_fragments(game_paths: dict[str, str] | None):
    """(game key, a distinctive lowercased path fragment) from settings.games --
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
    matchers: list[tuple[str, str]] = [
        (profile, n.lower())
        for profile, needles in (auto_detect or {}).items()
        for n in needles if n
    ]
    matchers += list(_path_fragments(game_paths))
    if not matchers:
        return None

    best_start, best_game = -1.0, None
    for cmd, start in _procs():
        if ".exe" not in cmd:            # not a live Windows game process
            continue
        for game, needle in matchers:
            i = cmd.find(needle)
            # needle must be a real path component (preceded by / or \) sitting
            # right next to a launched .exe -- an actual game invocation, not a
            # folder name quoted in a shell command or a long helper cmdline
            if i > 0 and cmd[i - 1] in "/\\" and ".exe" in cmd[i:i + 400]:
                if start > best_start:
                    best_start, best_game = start, game
                break                    # this process is accounted for
    return best_game
