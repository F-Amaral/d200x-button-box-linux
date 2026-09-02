"""Per-game config parsing + the games registry / dispatch."""

import json
import struct

import pytest

from d200x_button_box import games
from d200x_button_box.games import ac_evo, ac_rally, lmu


# --- registry / dispatch --------------------------------------------------- #
def test_registry_and_capabilities():
    av = games.available()
    assert av["lmu"]["can_read"] and av["lmu"]["can_write"]
    assert av["ac_rally"]["can_read"] and av["ac_rally"]["can_write"]
    assert av["ac_evo"]["can_read"] and av["ac_evo"]["can_write"]
    assert av["ac_rally"]["label"] == "AC Rally"


def test_detect_hints():
    h = games.detect_hints()
    assert h["lmu"] == ["LeMansUltimate"]
    assert "acr.exe" in h["ac_rally"]


def test_dispatch_errors(monkeypatch):
    with pytest.raises(ValueError):
        games.read("nope", "x")                 # unknown game
    with pytest.raises(ValueError):
        games.controls("nope", "x")
    with pytest.raises(ValueError):
        games.bind("nope", "x", "y", 1)

    # a game that declares no writer -> dispatch refuses before touching disk
    from d200x_button_box.games import Game
    monkeypatch.setitem(games.ALL, "toy", Game(key="toy", label="Toy", read=lambda p: {}))
    with pytest.raises(ValueError, match="cannot write"):
        games.bind("toy", "x", "y", 1)
    with pytest.raises(ValueError, match="cannot list controls"):
        games.controls("toy", "x")


# --- Le Mans Ultimate ---------------------------------------------------------#
def _lmu_tree(tmp_path):
    d = tmp_path / "UserData" / "player"
    d.mkdir(parents=True)
    (d / "direct input.json").write_text(json.dumps({
        "Devices": {
            "D200x Button Box-ABC123": {"layout": {"axes": 0, "buttons": 32, "povs": 0}},
            "Some Wheel-XYZ": {},
        },
        "Input": {
            "Headlights": {"device": "D200x Button Box-ABC123", "id": 32},   # -> button 1
            "Wipers": {"device": "D200x Button Box-ABC123", "id": 34},       # -> button 3
            "TC Down": {"device": "D200x Button Box-ABC123", "id": 48},      # -> button 17
            "Brake": {"device": "Some Wheel-XYZ", "id": 10},                 # ignored
        },
        "Alternative Input": {
            "Headlights Pulse": {"device": "D200x Button Box-ABC123", "id": 33},  # -> button 2
        },
    }))
    return tmp_path


def test_lmu_read_maps_ids_to_buttons(tmp_path):
    assert lmu.read(_lmu_tree(tmp_path)) == {
        1: ["Headlights"], 2: ["Headlights Pulse"], 3: ["Wipers"], 17: ["TC Down"]}
    # also via the dispatcher
    assert games.read("lmu", _lmu_tree(tmp_path / "b")) [1] == ["Headlights"]


def test_lmu_read_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        lmu.read(tmp_path)


def test_lmu_controls_and_write_roundtrip(tmp_path):
    tree = _lmu_tree(tmp_path)
    f = tree / "UserData" / "player" / "direct input.json"

    info = lmu.controls(tree)
    assert info["device_present"] is True
    assert "Headlights" in info["controls"] and "Brake" in info["controls"]
    assert info["bound"]["Headlights"] == 1

    res = lmu.write(tree, "Brake", 5)             # wheel control -> our button 5
    assert res["ok"]
    data = json.loads(f.read_text())
    assert data["Input"]["Brake"] == {"device": "D200x Button Box-ABC123", "id": 5 + 31}
    assert (tree / "UserData" / "player" / "direct input.json.d200x-bak").is_file()

    lmu.write(tree, "Brake", None)
    assert "Brake" not in json.loads(f.read_text())["Input"]


def test_lmu_write_refuses_when_device_absent(tmp_path):
    d = tmp_path / "UserData" / "player"
    d.mkdir(parents=True)
    (d / "direct input.json").write_text(json.dumps({"Devices": {}, "Input": {"Brake": {}}}))
    with pytest.raises(ValueError, match="not in the game's config"):
        lmu.write(tmp_path, "Brake", 1)


# --- Assetto Corsa Rally (UE5 GVAS SaveGame) -------------------------------- #
def _fstr(s: str) -> bytes:
    b = s.encode("latin1") + b"\x00"
    return struct.pack("<i", len(b)) + b


def _acr_sav(mappings, active="InputUserSettings.Profiles.Current2"):
    """Minimal blob mirroring the real .sav: an active-profile id, one key
    profile object, then a count-prefixed run of 4-FString + 6-byte mappings."""
    out = b"GVAS\x00\x00\x00\x00"
    out += _fstr("CurrentProfileIdentifier") + _fstr("TagName") + _fstr(active)
    out += _fstr("None")                                  # end tagged props
    out += _fstr(active)                                  # the profile map key
    out += _fstr("/Script/acr.AcrEnhancedPlayerMappableKeyProfile")
    out += _fstr("AcrEnhancedPlayerMappableKeyProfile_2147000001")
    out += b"\x00" + struct.pack("<i", len(mappings))
    for action, key in mappings:
        out += _fstr(action) + _fstr(key) + _fstr("RawInput") + _fstr("SteeringWheel")
        out += b"\x05\x00\x00\x00\x00\x00"                # the constant trailer the game writes
    out += _fstr("ProfileIdentifier") + _fstr("ObjectEnd")
    return out


def test_ac_rally_read_maps_our_device_buttons(tmp_path):
    sav = tmp_path / "EnhancedInputUserSettings.sav"
    sav.write_bytes(_acr_sav([
        ("CycleLights", "GenericUSBController_Button1_1209_D200"),   # -> button 1
        ("CycleWipers", "GenericUSBController_Button3_1209_D200"),   # -> button 3
        ("Handbrake", "GenericUSBController_Button22_346E_0002"),    # MOZA -> ignored
        ("GearUp", "None"),                                          # unbound -> ignored
    ]))
    assert ac_rally.read(sav) == {1: ["Cycle Lights"], 3: ["Cycle Wipers"]}  # CamelCase split


def test_ac_rally_read_accepts_a_directory(tmp_path):
    sav = tmp_path / ac_rally._SAV_REL
    sav.parent.mkdir(parents=True)
    sav.write_bytes(_acr_sav([("Respawn", "GenericUSBController_Button7_1209_D200")]))
    assert ac_rally.read(tmp_path) == {7: ["Respawn"]}


# --- Assetto Corsa EVO (protobuf input_devices.inputdeviceconfiguration) ---- #
def _pbv(n):                       # varint
    out = b""
    while True:
        b, n = n & 0x7F, n >> 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _pbld(fn, payload):           # length-delimited field
    return _pbv((fn << 3) | 2) + _pbv(len(payload)) + payload


def _pbvi(fn, val):               # varint field
    return _pbv((fn << 3) | 0) + _pbv(val)


def _acevo_cfg(mappings):
    """One device (our deck) with `mappings` = [(control_id, dir_or_None, button)]."""
    ident = _pbld(1, b"D200x Button Box") + _pbld(5, ac_evo._DECK_GUID.encode())
    dev = _pbld(1, ident)
    for cid, direction, button in mappings:
        ctl = _pbvi(1, cid) + _pbvi(5, cid)
        if direction is not None:
            ctl += _pbvi(3, direction)
        m = _pbld(1, ctl)
        if button - 1:                       # button0 == 0 is omitted (proto default)
            m += _pbvi(2, button - 1)
        dev += _pbld(2, m)
    return _pbld(1, dev)


def test_ac_evo_read(tmp_path):
    cfg = tmp_path / "input_devices.inputdeviceconfiguration"
    cfg.write_bytes(_acevo_cfg([
        (132, None, 2),      # Indicator Left  -> button 2
        (133, None, 3),      # Indicator Right -> button 3
        (121, None, 1),      # Flashing Lights -> button 1 (button0 omitted)
        (120, 2, 1),         # Cycle Lights +  -> button 1
        (120, 1, 6),         # Cycle Lights -  -> button 6
        (9999, None, 8),     # unknown control id -> still labels the button
    ]))
    assert ac_evo.read(cfg) == {
        1: ["Flashing Lights", "Cycle Lights +"],
        2: ["Indicator Left"],
        3: ["Indicator Right"],
        6: ["Cycle Lights -"],
        8: ["control 9999"],
    }


def test_ac_rally_write_splices_hardwarekey(tmp_path):
    sav = tmp_path / "EnhancedInputUserSettings.sav"
    sav.write_bytes(_acr_sav([
        ("Handbrake", "GenericUSBController_Button22_346E_0002"),  # on the wheel
        ("Respawn", "None"),                                       # unbound
        ("GearUp", "GenericUSBController_Button5_1209_D200"),      # already on our btn 5
    ]))

    # bind Handbrake -> our button 5; GearUp (also btn 5) gets cleared
    res = ac_rally.write(sav, "Handbrake", 5)
    assert res["ok"] and (tmp_path / "EnhancedInputUserSettings.sav.d200x-bak").is_file()
    ctl = ac_rally.controls(sav)
    assert ctl["bound"] == {"Handbrake": 5}
    assert ac_rally.read(sav) == {5: ["Handbrake"]}

    # clear it again
    ac_rally.write(sav, "Handbrake", None)
    assert ac_rally.controls(sav)["bound"] == {}

    with pytest.raises(ValueError, match="unknown control"):
        ac_rally.write(sav, "NoSuchAction", 1)


def test_ac_evo_write_splices_the_device_block(tmp_path):
    cfg = tmp_path / "input_devices.inputdeviceconfiguration"
    cfg.write_bytes(_acevo_cfg([
        (132, None, 2),      # Indicator Left -> button 2
        (139, None, 6),      # Horn -> button 6
    ]))

    ac_evo.write(cfg, "Horn", 10)                 # move Horn 6 -> 10
    assert (tmp_path / "input_devices.inputdeviceconfiguration.d200x-bak").is_file()
    assert ac_evo.read(cfg) == {2: ["Indicator Left"], 10: ["Horn"]}

    ac_evo.write(cfg, "Ignition", 4)              # new binding
    assert ac_evo.read(cfg) == {2: ["Indicator Left"], 10: ["Horn"], 4: ["Ignition"]}

    ac_evo.write(cfg, "Horn", None)               # clear
    assert 10 not in ac_evo.read(cfg)

    # an un-named id is bindable too (shows as "control <id>" until named)
    ac_evo.write(cfg, "control 415", 7)
    assert ac_evo.read(cfg)[7] == ["control 415"]
    with pytest.raises(ValueError, match="cannot resolve"):
        ac_evo.write(cfg, "Nonsense", 1)


def _acevo_multi_device(devices):
    """devices = [(name, guid, [(cid, dir, button), ...]), ...]."""
    out = b""
    for name, guid, mappings in devices:
        ident = _pbld(1, name.encode()) + _pbld(5, guid.encode())
        dev = _pbld(1, ident)
        for cid, direction, button in mappings:
            ctl = _pbvi(1, cid) + _pbvi(5, cid) + (_pbvi(3, direction) if direction else b"")
            m = _pbld(1, ctl) + (_pbvi(2, button - 1) if button > 1 else b"")
            dev += _pbld(2, m)
        out += _pbld(1, dev)
    return out


def test_ac_evo_controls_lists_ids_from_all_devices(tmp_path):
    cfg = tmp_path / "input_devices.inputdeviceconfiguration"
    cfg.write_bytes(_acevo_multi_device([
        ("Some Wheel", "{FFFF0000-0000-0000-0000-000000000000}", [(140, None, 3), (169, None, 4)]),
        ("D200x Button Box", ac_evo._DECK_GUID, [(139, None, 6)]),   # Horn
    ]))
    # sibling keyboard file (flat Mapping list; field 1 there is a header)
    (tmp_path / "input_keyboard.keyboardinputconfiguration").write_bytes(
        b"\x0a\x03\x10\x11\x12"
        + _pbld(2, _pbld(1, _pbvi(1, 300) + _pbvi(5, 300)))
        + _pbld(2, _pbld(1, _pbvi(1, 415) + _pbvi(5, 415))))
    info = ac_evo.controls(cfg)
    assert "Horn" in info["controls"]              # our named set
    assert "control 140" in info["controls"]       # bound on the wheel
    assert "control 169" in info["controls"]
    assert "control 300" in info["controls"]       # from the keyboard file
    assert "control 415" in info["controls"]
    assert info["bound"]["Horn"] == 6


def test_ac_evo_learns_names_from_deck_labels(tmp_path, monkeypatch):
    from d200x_button_box import config

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    cfg = tmp_path / "input_devices.inputdeviceconfiguration"
    cfg.write_bytes(_acevo_cfg([
        (415, None, 5),      # unnamed control on button 5
        (139, None, 6),      # Horn (already named) on button 6
        (120, 1, 7),         # bipolar half -- name is ambiguous, skip
    ]))

    # labels the user typed on the deck keys for those buttons
    ac_evo.learn(cfg, {5: "Look Left", 6: "My Horn", 7: "Lights Down"})

    names = ac_evo._names()
    assert names[415] == "Look Left"     # learned
    assert names[139] == "Horn"          # not overwritten (was already named)
    assert 120 not in ac_evo._learned()  # bipolar skipped
    assert ac_evo.read(cfg)[5] == ["Look Left"]

    # a second learn doesn't clobber the first
    ac_evo.learn(cfg, {5: "Something Else"})
    assert ac_evo._names()[415] == "Look Left"
