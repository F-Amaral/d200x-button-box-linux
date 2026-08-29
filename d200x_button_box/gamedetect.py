"""Guess which game is running by scanning process command lines.

`auto_detect` in settings maps a profile name to a list of case-insensitive
substrings; the first profile whose substrings appear in any running command
line wins. Cheap enough to call every few seconds.
"""

from __future__ import annotations

import glob


def _cmdlines() -> list[str]:
    out = []
    for path in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(path, "rb") as f:
                out.append(f.read().replace(b"\x00", b" ").decode("utf-8", "replace").lower())
        except OSError:
            continue
    return out


def detect(auto_detect: dict[str, list[str]]) -> str | None:
    if not auto_detect:
        return None
    cmds = _cmdlines()
    for profile, needles in auto_detect.items():
        for needle in needles:
            n = needle.lower()
            if any(n in cmd for cmd in cmds):
                return profile
    return None
