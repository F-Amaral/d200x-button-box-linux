"""Per-game config parsing + the games registry / dispatch."""

import json
import struct

import pytest

from d200x_button_box import games
from d200x_button_box.games import ac_rally, lmu


# --- registry / dispatch --------------------------------------------------- #
def test_registry_and_capabilities():
    av = games.available()
    assert av["lmu"]["can_read"] and av["lmu"]["can_write"]
    assert av["ac_rally"]["can_read"] and not av["ac_rally"]["can_write"]
    assert not av["ac_evo"]["can_read"] and not av["ac_evo"]["can_write"]
    assert av["ac_rally"]["label"] == "AC Rally"


def test_detect_hints():
    h = games.detect_hints()
    assert h["lmu"] == ["LeMansUltimate"]
    assert "acr.exe" in h["ac_rally"]


def test_dispatch_errors_for_missing_capability():
    with pytest.raises(ValueError):
        games.bind("ac_rally", "x", "y", 1)      # no writer
    with pytest.raises(ValueError):
        games.read("ac_evo", "x")               # no importer
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


def _acr_sav(mappings):
    """Minimal blob with the same FString run the real .sav uses per mapping."""
    out = b"GVAS_fake_header\x00\x01\x02\x03"
    for action, key in mappings:
        out += _fstr(action) + _fstr(key) + _fstr("RawInput") + _fstr("SteeringWheel")
        out += b"\x05\x00\x00\x00\x00\x00"       # the constant trailer the game writes
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
