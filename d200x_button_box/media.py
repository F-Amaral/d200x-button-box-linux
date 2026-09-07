"""Media / volume control through the standard Linux CLIs -- no new dependency.

* ``wpctl`` (WirePlumber) or ``pactl`` (PulseAudio) -- default-sink volume + mute
* ``playerctl`` -- MPRIS transport (play/pause/next/prev/stop) + now-playing

Each part degrades to a no-op / blank when its tool isn't installed. Volume via
D-Bus/PipeWire doesn't care which window has focus, so it works under
gamescope / VR where the media keys don't.
"""

from __future__ import annotations

import shutil
import subprocess
import time

_SINK = "@DEFAULT_AUDIO_SINK@"
ACTIONS = ("volume_up", "volume_down", "mute", "playpause", "next", "previous", "stop")
_TRANSPORT = {"playpause": "play-pause", "next": "next", "previous": "previous", "stop": "stop"}


def _run(*args: str, capture: bool = False) -> str | None:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=2)
        return (r.stdout or "").strip() if capture else None
    except (OSError, subprocess.SubprocessError):
        return None


def fire(action: str, step: int = 5) -> None:
    """Do one media / volume action. Unknown action or missing tool -> no-op."""
    step = max(1, min(50, int(step or 5)))
    if action in ("volume_up", "volume_down", "mute"):
        if shutil.which("wpctl"):
            if action == "mute":
                _run("wpctl", "set-mute", _SINK, "toggle")
            else:
                _run("wpctl", "set-volume", "-l", "1.5", _SINK,
                     f"{step}%{'+' if action == 'volume_up' else '-'}")
        elif shutil.which("pactl"):
            if action == "mute":
                _run("pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle")
            else:
                _run("pactl", "set-sink-volume", "@DEFAULT_SINK@",
                     f"{'+' if action == 'volume_up' else '-'}{step}%")
    elif action in _TRANSPORT and shutil.which("playerctl"):
        _run("playerctl", _TRANSPORT[action])


_cache: dict = {"t": -99.0, "v": {}}


def status() -> dict:
    """{title, artist, player, playing, volume, muted} for `widget: media`,
    cached ~1.5 s so it's cheap to call from a widget render / layout push.
    `playing` is None when nothing is playing; `volume` is 0-150 or None."""
    now = time.monotonic()
    if now - _cache["t"] > 1.5:
        _cache["v"] = _status()
        _cache["t"] = now
    return _cache["v"]


def _status() -> dict:
    out: dict = {"title": "", "artist": "", "player": "", "playing": None,
                 "volume": None, "muted": False}
    if shutil.which("playerctl"):
        meta = _run("playerctl", "metadata", "--format",
                    "{{title}}\t{{artist}}\t{{playerName}}\t{{status}}", capture=True)
        if meta:
            f = (meta.split("\t") + ["", "", "", ""])[:4]
            out.update(title=f[0], artist=f[1], player=f[2],
                       playing=(f[3].lower() == "playing") if f[3] else None)
    vol = _run("wpctl", "get-volume", _SINK, capture=True)   # "Volume: 0.85 [MUTED]"
    if vol and "Volume:" in vol:
        try:
            out["muted"] = "MUTED" in vol
            out["volume"] = max(0, min(150, round(float(vol.split()[1]) * 100)))
        except (ValueError, IndexError):
            pass
    return out
