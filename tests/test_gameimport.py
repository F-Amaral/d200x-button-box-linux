"""Game-binding import (Le Mans Ultimate)."""

import json

from d200x_button_box import config, gameimport


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


def test_import_lmu_maps_ids_to_buttons(tmp_path):
    m = gameimport.import_lmu(_lmu_tree(tmp_path))
    assert m == {1: ["Headlights"], 2: ["Headlights Pulse"], 3: ["Wipers"], 17: ["TC Down"]}


def test_import_lmu_missing_file(tmp_path):
    try:
        gameimport.import_lmu(tmp_path)
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")


def test_apply_labels_to_keys_and_knobs():
    prof = config.Profile(name="t", pages=[config.Page(
        keys={0: {"gamepad": 1}, 1: {"gamepad": 2, "label": "manual"}},
        knobs={17: {"press": {"gamepad": 17}}},
    )])
    rep = gameimport.apply_labels(prof, {1: ["Headlights"], 2: ["Wipers"], 17: ["TC Down"], 9: ["Ghost"]},
                                  overwrite=False)
    assert prof.pages[0].keys[0]["label"] == "Headlights"
    assert prof.pages[0].keys[1]["label"] == "manual"          # kept, no overwrite
    assert prof.pages[0].knobs[17]["press"]["label"] == "TC Down"
    assert rep["skipped"] == {2: "Wipers"}
    assert rep["unmatched"] == {9: "Ghost"}


def test_apply_labels_overwrite():
    prof = config.Profile(name="t", pages=[config.Page(keys={0: {"gamepad": 1, "label": "old"}})])
    gameimport.apply_labels(prof, {1: ["New"]}, overwrite=True)
    assert prof.pages[0].keys[0]["label"] == "New"


def test_lmu_controls_and_bind_roundtrip(tmp_path):
    import json

    tree = _lmu_tree(tmp_path)
    f = tree / "UserData" / "player" / "direct input.json"

    info = gameimport.lmu_controls(tree)
    assert info["device_present"] is True
    assert "Headlights" in info["controls"] and "Brake" in info["controls"]
    assert info["bound"]["Headlights"] == 1

    # bind "Brake" (currently on the wheel) to our button 5
    res = gameimport.lmu_bind(tree, "Brake", 5)
    assert res["ok"]
    data = json.loads(f.read_text())
    assert data["Input"]["Brake"] == {"device": "D200x Button Box-ABC123", "id": 5 + 31}
    assert (tree / "UserData" / "player" / "direct input.json.d200x-bak").is_file()

    # clear it
    gameimport.lmu_bind(tree, "Brake", None)
    assert "Brake" not in json.loads(f.read_text())["Input"]


def test_lmu_bind_refuses_when_device_absent(tmp_path):
    import json

    d = tmp_path / "UserData" / "player"
    d.mkdir(parents=True)
    (d / "direct input.json").write_text(json.dumps({"Devices": {}, "Input": {"Brake": {}}}))
    try:
        gameimport.lmu_bind(tmp_path, "Brake", 1)
    except ValueError as e:
        assert "not in the game's config" in str(e)
        return
    raise AssertionError("expected ValueError")


# --- Assetto Corsa Rally (UE5 GVAS SaveGame) -------------------------------- #
def _fstr(s: str) -> bytes:
    import struct

    b = s.encode("latin1") + b"\x00"
    return struct.pack("<i", len(b)) + b


def _acr_sav(mappings: list[tuple[str, str]]) -> bytes:
    """Minimal blob with the same FString run the real .sav uses per mapping."""
    out = b"GVAS_fake_header\x00\x01\x02\x03"
    for action, key in mappings:
        out += _fstr(action) + _fstr(key) + _fstr("RawInput") + _fstr("SteeringWheel")
        out += b"\x05\x00\x00\x00\x00\x00"  # the constant trailer the game writes
    return out


def test_import_ac_rally_maps_our_device_buttons(tmp_path):
    sav = tmp_path / "EnhancedInputUserSettings.sav"
    sav.write_bytes(_acr_sav([
        ("CycleLights", "GenericUSBController_Button1_1209_D200"),   # -> button 1
        ("CycleWipers", "GenericUSBController_Button3_1209_D200"),   # -> button 3
        ("Handbrake", "GenericUSBController_Button22_346E_0002"),    # MOZA -> ignored
        ("GearUp", "None"),                                          # unbound -> ignored
    ]))
    # CamelCase action names are split for readable labels
    assert gameimport.import_ac_rally(sav) == {1: ["Cycle Lights"], 3: ["Cycle Wipers"]}


def test_import_ac_rally_accepts_a_directory(tmp_path):
    sav = tmp_path / gameimport._ACR_SAV_REL
    sav.parent.mkdir(parents=True)
    sav.write_bytes(_acr_sav([("Respawn", "GenericUSBController_Button7_1209_D200")]))
    assert gameimport.import_ac_rally(tmp_path) == {7: ["Respawn"]}


def test_prune_to_buttons_drops_unbound_keys():
    from d200x_button_box import config

    prof = config.default_profile("acr")
    n_before = len(prof.pages[0].keys)
    gameimport.prune_to_buttons(prof, {1, 3})
    assert set(prof.pages[0].keys) == {0, 2}          # only the kept buttons' keys
    assert n_before > 2
    assert prof.pages[0].knobs == {}                  # encoder subs all pruned
