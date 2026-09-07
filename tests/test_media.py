"""media / volume control -- CLI dispatch + now-playing parse (tools mocked)."""

from d200x_button_box import media, widgets


def _mock(monkeypatch, which=("wpctl", "playerctl"), outputs=None):
    calls = []
    monkeypatch.setattr(media.shutil, "which", lambda c: c if c in which else None)

    class R:
        def __init__(self, out=""):
            self.stdout = out

    def run(args, **kw):
        calls.append(list(args))
        key = args[0] + (" " + args[1] if len(args) > 1 else "")
        return R((outputs or {}).get(key, ""))

    monkeypatch.setattr(media.subprocess, "run", run)
    media._cache["t"] = -99.0
    return calls


def test_fire_volume_via_wpctl(monkeypatch):
    calls = _mock(monkeypatch)
    media.fire("volume_up", step=3)
    media.fire("volume_down")
    media.fire("mute")
    assert calls == [
        ["wpctl", "set-volume", "-l", "1.5", "@DEFAULT_AUDIO_SINK@", "3%+"],
        ["wpctl", "set-volume", "-l", "1.5", "@DEFAULT_AUDIO_SINK@", "5%-"],
        ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
    ]


def test_fire_transport_via_playerctl(monkeypatch):
    calls = _mock(monkeypatch)
    media.fire("playpause")
    media.fire("next")
    assert calls == [["playerctl", "play-pause"], ["playerctl", "next"]]


def test_fire_falls_back_to_pactl(monkeypatch):
    calls = _mock(monkeypatch, which=("pactl",))
    media.fire("volume_up", step=10)
    assert calls == [["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"]]


def test_fire_noop_without_tools(monkeypatch):
    calls = _mock(monkeypatch, which=())
    media.fire("volume_up")
    media.fire("playpause")
    assert calls == []


def test_status_parse(monkeypatch):
    _mock(monkeypatch, outputs={
        "playerctl metadata": "Song Title\tThe Band\tspotify\tPlaying",
        "wpctl get-volume": "Volume: 0.85 [MUTED]",
    })
    st = media.status()
    assert st == {"title": "Song Title", "artist": "The Band", "player": "spotify",
                  "playing": True, "volume": 85, "muted": True}
    assert widgets._media_lines(st) == ["Song Title", "The Band", "playing · muted"]


def test_status_nothing_playing(monkeypatch):
    _mock(monkeypatch, outputs={"wpctl get-volume": "Volume: 1.00"})
    st = media.status()
    assert st["playing"] is None and st["volume"] == 100 and st["title"] == ""
    assert widgets._media_lines(st) == ["— nothing playing —", "system audio", "vol 100%"]
