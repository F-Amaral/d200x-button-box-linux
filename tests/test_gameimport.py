"""Applying a game import to a deck profile (apply_labels / prune_to_buttons)."""

from d200x_button_box import config, gameimport


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


def test_prune_to_buttons_drops_unbound_keys():
    prof = config.default_profile("acr")
    n_before = len(prof.pages[0].keys)
    gameimport.prune_to_buttons(prof, {1, 3})
    assert set(prof.pages[0].keys) == {0, 2}          # only the kept buttons' keys
    assert n_before > 2
    assert prof.pages[0].knobs == {}                  # encoder subs all pruned
