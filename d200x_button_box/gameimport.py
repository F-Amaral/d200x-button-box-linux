"""Apply a game import to a deck profile.

`games.read(<game>, path)` returns a `{button: [control names]}` map;
`apply_labels` folds that into a `config.Profile`. Per-game config parsing lives
in the `games/` package, not here.
"""

from __future__ import annotations


def apply_labels(profile, button_names: dict[int, list[str]], overwrite: bool = True) -> dict:
    """Set labels from an import map (LCD keys + knob sub-bindings, the latter
    shown only in the editor). Returns a report of what changed."""
    applied: dict[int, str] = {}
    skipped: dict[int, str] = {}
    seen: set[int] = set()

    def annotate(b: dict) -> None:
        n = b.get("gamepad")
        if not isinstance(n, int):
            return
        seen.add(n)
        names = button_names.get(n)
        if not names:
            return
        label = " / ".join(names)
        if b.get("label") and not overwrite:
            skipped[n] = label
        else:
            b["label"] = label
            applied[n] = label

    for page in profile.pages:
        for b in page.keys.values():
            annotate(b)
        for knob in page.knobs.values():
            for sub in knob.values():
                if isinstance(sub, dict):
                    annotate(sub)

    unmatched = {n: " / ".join(v) for n, v in button_names.items() if n not in seen}
    return {"applied": applied, "skipped": skipped, "unmatched": unmatched}
