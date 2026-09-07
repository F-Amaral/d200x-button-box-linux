"""Game-process detection: needle hints + install-path fallback."""

from d200x_button_box import gamedetect


def _procs(*procs, monkeypatch):
    """procs: "cmdline" strings, or ("cmdline", start_ticks) tuples."""
    norm = [(p if isinstance(p, tuple) else (p, 0.0)) for p in procs]
    monkeypatch.setattr(gamedetect, "_procs", lambda: [(c.lower(), float(s)) for c, s in norm])


def test_needle_match(monkeypatch):
    _procs("/usr/bin/proton run /games/Le Mans Ultimate/Le Mans Ultimate.exe", monkeypatch=monkeypatch)
    assert gamedetect.detect({"lmu": ["Le Mans Ultimate"]}) == "lmu"
    assert gamedetect.detect({"lmu": ["LeMansUltimate"]}) is None   # the wrong hint misses


def test_install_path_fallback(monkeypatch):
    _procs("reaper SteamLaunch AppId=2399420 -- /mnt/lib/steamapps/common/Le Mans Ultimate/start_protected_game.exe",
           monkeypatch=monkeypatch)
    assert gamedetect.detect({"lmu": ["nope"]},
                             {"lmu": "/mnt/lib/steamapps/common/Le Mans Ultimate"}) == "lmu"


def test_compatdata_fallback(monkeypatch):
    _procs("proton /home/u/.steam/steamapps/compatdata/3058630/pfx/drive_c/game.exe", monkeypatch=monkeypatch)
    cfg = "/home/u/.steam/steamapps/compatdata/3058630/pfx/.../input_devices.inputdeviceconfiguration"
    assert gamedetect.detect(None, {"ac_evo": cfg}) == "ac_evo"


def test_nothing_running(monkeypatch):
    _procs("/usr/bin/firefox", "/usr/lib/systemd/systemd", monkeypatch=monkeypatch)
    assert gamedetect.detect({"lmu": ["Le Mans Ultimate"]}, {"lmu": "/x/steamapps/common/Le Mans Ultimate"}) is None
    assert gamedetect.detect() is None


def test_non_exe_process_referencing_the_folder_does_not_match(monkeypatch):
    # a file manager / shell sitting in the game folder must not count as running
    _procs("nautilus /mnt/lib/steamapps/common/Le Mans Ultimate", monkeypatch=monkeypatch)
    assert gamedetect.detect({"lmu": ["Le Mans Ultimate"]}) is None


def test_folder_name_quoted_in_a_shell_command_does_not_match(monkeypatch):
    # a grep / git command mentioning the game is not the game running
    _procs('/bin/zsh -c grep -r "Le Mans Ultimate" . && ./build.exe', monkeypatch=monkeypatch)
    assert gamedetect.detect({"lmu": ["Le Mans Ultimate"]}) is None


def test_deep_compatdata_path_still_matches(monkeypatch):
    cmd = ("/x/steamapps/compatdata/3058630/pfx/drive_c/Program Files (x86)/Steam/"
           "steamapps/common/Assetto Corsa EVO/AssettoCorsaEVO.exe")
    _procs(cmd, monkeypatch=monkeypatch)
    assert gamedetect.detect(None, {"ac_evo": "/x/steamapps/compatdata/3058630"}) == "ac_evo"


def test_lingering_old_game_loses_to_the_freshly_launched_one(monkeypatch):
    ad = {"lmu": ["Le Mans Ultimate"], "ac_rally": ["acr.exe"]}
    # LMU wine processes still tearing down (old), AC Rally just launched (new)
    _procs(
        ("Z:/games/Le Mans Ultimate/Le Mans Ultimate.exe", 1000),
        ("wineserver /games/Le Mans Ultimate", 1000),          # no .exe -> ignored anyway
        ("proton run /games/Assetto Corsa Rally/acr.exe", 9000),
        monkeypatch=monkeypatch,
    )
    assert gamedetect.detect(ad) == "ac_rally"
