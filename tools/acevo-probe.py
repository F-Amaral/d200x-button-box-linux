#!/usr/bin/env python3
"""Discover AC EVO control names.

AC EVO's content is a 69 GB encrypted pack -- there's no readable list of what
each in-game control id *is*. This binds unnamed control ids to virtual-gamepad
buttons, so you open AC EVO once, walk the controls menu, and read off which
action landed on "Button N". Then --names bakes what you saw.

    tools/acevo-probe.py                  # bind the next batch, print the map
    tools/acevo-probe.py --names notes.txt  # merge '<button> <name>' lines
    tools/acevo-probe.py --clear           # undo the current batch

The virtual pad has 40 buttons, so this works in batches of 38. Before probing,
switch the deck to a NON-AC-EVO profile (so the daemon's live sync doesn't grab
the probe bindings), and close AC EVO (it reads the config at startup). A
one-time .d200x-bak sits next to the config. Repeat until "nothing left".
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d200x_button_box.games import ac_evo  # noqa: E402

BATCH = 38   # <= pad button count (40), a couple spare


def _sidecar() -> Path:
    from d200x_button_box.config import CONFIG_DIR
    return CONFIG_DIR / ".acevo_probe.json"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clear", action="store_true", help="unbind the current probe batch")
    ap.add_argument("--names", metavar="FILE", help="merge '<button> <name>' lines into game_names.yaml")
    ap.add_argument("--path", help="AC EVO config file or its folder (default: auto-locate)")
    args = ap.parse_args()

    path = args.path or ac_evo.find()
    if not path:
        sys.exit("AC EVO config not found -- pass --path")
    cfg = ac_evo._cfg_path(path)
    side = _sidecar()
    layout = {int(k): v for k, v in json.loads(side.read_text()).items()} if side.is_file() else {}

    if args.names:
        if not layout:
            sys.exit("no active probe batch -- run the probe first")
        add = {}
        for line in Path(args.names).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            btn, _, name = line.partition(" ")
            cid = layout.get(int(btn))
            if cid is not None and name.strip():
                add[cid] = name.strip()
        ac_evo._remember(add)
        print(f"remembered {len(add)} names in game_names.yaml")
        return

    if args.clear:
        for btn, cid in layout.items():
            ac_evo.write(cfg, f"control {cid}", None)
        side.unlink(missing_ok=True)
        print(f"cleared {len(layout)} probe bindings")
        return

    unknown = [int(c.split()[1]) for c in ac_evo.controls(cfg)["controls"] if c.startswith("control ")]
    if not unknown:
        side.unlink(missing_ok=True)
        sys.exit("no unnamed controls left -- all discovered")

    batch = unknown[:BATCH]
    layout = {i + 1: cid for i, cid in enumerate(batch)}
    for btn, cid in layout.items():
        ac_evo.write(cfg, f"control {cid}", btn)
        print(f"  button {btn:>2}  <-  control {cid}")
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text(json.dumps(layout))
    left = len(unknown) - len(batch)
    print(f"\n{len(batch)} bound ({left} still unnamed). Open AC EVO -> controls menu, "
          "note the action on each button, then:\n"
          "  tools/acevo-probe.py --names notes.txt\n"
          "  tools/acevo-probe.py --clear      # then re-run for the next batch")


if __name__ == "__main__":
    main()
