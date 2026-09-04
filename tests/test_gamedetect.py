"""Game-process detection: needle hints + install-path fallback."""

from d200x_button_box import gamedetect


def _cmds(*lines, monkeypatch):
    monkeypatch.setattr(gamedetect, "_cmdlines", lambda: [x.lower() for x in lines])


def test_needle_match(monkeypatch):
    _cmds("/usr/bin/proton run /games/Le Mans Ultimate/Le Mans Ultimate.exe", monkeypatch=monkeypatch)
    assert gamedetect.detect({"lmu": ["Le Mans Ultimate"]}) == "lmu"
    assert gamedetect.detect({"lmu": ["LeMansUltimate"]}) is None   # the wrong hint misses


def test_install_path_fallback(monkeypatch):
    _cmds("reaper SteamLaunch AppId=2399420 -- /mnt/lib/steamapps/common/Le Mans Ultimate/start_protected_game.exe",
          monkeypatch=monkeypatch)
    # even with a useless needle, the Steam folder path is matched
    assert gamedetect.detect({"lmu": ["nope"]},
                             {"lmu": "/mnt/lib/steamapps/common/Le Mans Ultimate"}) == "lmu"


def test_compatdata_fallback(monkeypatch):
    _cmds("proton /home/u/.steam/steamapps/compatdata/3058630/pfx/drive_c/game.exe", monkeypatch=monkeypatch)
    cfg = "/home/u/.steam/steamapps/compatdata/3058630/pfx/.../input_devices.inputdeviceconfiguration"
    assert gamedetect.detect(None, {"ac_evo": cfg}) == "ac_evo"


def test_nothing_running(monkeypatch):
    _cmds("/usr/bin/firefox", "/usr/lib/systemd/systemd", monkeypatch=monkeypatch)
    assert gamedetect.detect({"lmu": ["Le Mans Ultimate"]}, {"lmu": "/x/steamapps/common/Le Mans Ultimate"}) is None
    assert gamedetect.detect() is None
