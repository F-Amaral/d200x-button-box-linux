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
