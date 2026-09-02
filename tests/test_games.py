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
    assert av["ac_evo"]["can_read"] and not av["ac_evo"]["can_write"]
    assert av["ac_rally"]["label"] == "AC Rally"


def test_detect_hints():
    h = games.detect_hints()
    assert h["lmu"] == ["LeMansUltimate"]
    assert "acr.exe" in h["ac_rally"]


def test_dispatch_errors_for_missing_capability():
    with pytest.raises(ValueError):
        games.bind("ac_evo", "x", "y", 1)       # no writer
    with pytest.raises(ValueError):
        games.controls("ac_evo", "x")           # no controls lister
    with pytest.raises(ValueError):
        games.controls("nope", "x")             # unknown game


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


def test_ac_rally_write_via_dispatch_blocked_for_missing_capability():
    # ac_evo has no writer
    with pytest.raises(ValueError):
        games.bind("ac_evo", "x", "y", 1)
