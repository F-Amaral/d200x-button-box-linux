"""Assetto Corsa EVO -- controls are an undocumented binary protobuf
(`Saved Games/ACE/input_devices.inputdeviceconfiguration`), so there is no
importer yet. This module only provides process detection + install discovery,
so an AC EVO profile can be auto-activated and shown as "linked, no import yet".
"""

from __future__ import annotations

from . import Game
from .steam import libraries


def find() -> str | None:
    for lib in libraries():
        p = lib / "common" / "Assetto Corsa EVO"
        if p.is_dir():
            return str(p)
    return None


GAME = Game(key="ac_evo", label="AC EVO", detect=("AssettoCorsaEVO", "acevo"), find=find)
