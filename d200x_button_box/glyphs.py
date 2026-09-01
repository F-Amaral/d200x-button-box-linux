"""Glyph names for key icons.

Two sources, both bundled:
  - ISO 7000 automotive tell-tales (public domain PNGs, `assets/telltales/`) --
    used for car / sim controls; see `telltales.py`.
  - Material Icons Round (Apache-2.0 font, `assets/`) -- nav, utility, media.

`render_icon` prefers a tell-tale; `NAME_TO_CP` maps the Material fallbacks.
`action_glyph` / `label_glyph` drive automatic icon selection. The pickable
name lists come straight from `telltales.names()` + `NAME_TO_CP`.
"""

from __future__ import annotations

from pathlib import Path

FONT_PATH = Path(__file__).parent / "assets" / "MaterialIconsRound-Regular.otf"

# short name -> codepoint, for glyphs NOT covered by the tell-tale PNG set
NAME_TO_CP: dict[str, int] = {
    "chevron_left": 0xE5CB, "chevron_right": 0xE5CC,
    "chevron_up": 0xE316, "chevron_down": 0xE313,       # keyboard_arrow_*
    "arrow_up": 0xF1E0, "arrow_down": 0xF1E3,           # north / south
    "arrow_left": 0xF1E6, "arrow_right": 0xF1DF,        # west / east
    "arrow_back": 0xE5C4,
    "home": 0xE88A, "layers": 0xE53B, "refresh": 0xE5D5, "back": 0xE5C4,
    "apps": 0xE5C3, "grid": 0xE9B0, "menu": 0xE5D2, "swap": 0xE8D4,
    "settings": 0xE8B8, "tune": 0xE429, "build": 0xE869, "terminal": 0xEB8E,
    "power": 0xE8AC, "gamepad": 0xE30F, "warning_tri": 0xE002,
    "check": 0xE5CA, "close": 0xE5CD, "add": 0xE145, "remove": 0xE15B,
    "star": 0xE838, "circle": 0xEF4A, "timer": 0xE425, "eye": 0xE8F4,
    "navigation": 0xE55D, "speed": 0xE9E4, "bolt": 0xEA0B,
    "volume": 0xE050, "mic": 0xE029, "chat": 0xE0B7, "radio": 0xE03E,
    "flag": 0xE153, "checkered_flag": 0xF06E, "heat": 0xE80E, "cold": 0xEB3B,
}

ALIASES = {
    "next": "chevron_right", "prev": "chevron_left", "previous": "chevron_left",
    "up": "arrow_up", "down": "arrow_down", "left": "arrow_left", "right": "arrow_right",
    "page": "layers", "profile": "swap", "launcher": "apps", "auto": "refresh",
    "pit": "flag", "vr": "eye",
}


def codepoint(name: str) -> int | None:
    name = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if name in NAME_TO_CP:
        return NAME_TO_CP[name]
    if name in ALIASES:
        return NAME_TO_CP.get(ALIASES[name])
    return None




# --- automatic selection --------------------------------------------------
def action_glyph(binding: dict) -> str | None:
    """Glyph implied by a binding's action (nav / meta keys)."""
    if not isinstance(binding, dict):
        return None
    if "page" in binding:
        v = str(binding["page"]).lower()
        return "prev" if v in ("prev", "previous") else "next" if v == "next" else "page"
    if "profile" in binding:
        v = str(binding["profile"]).lower()
        return {"home": "home", "auto": "refresh", "next": "swap", "prev": "swap"}.get(v, "profile")
    if "command" in binding:
        return "terminal"
    return None


# label substring -> glyph name. Most map to an ISO tell-tale PNG; a handful
# fall back to a Material glyph. First match wins, so order specific -> generic.
_LABEL_HINTS = [
    # lighting
    ("high beam", "hl_high"), ("full beam", "hl_high"), ("main beam", "hl_high"),
    ("beam flash", "hl_high"), ("flash", "hl_high"),
    ("headlight pulse", "hl_high"), ("headlamp flash", "hl_high"), ("pulse", "hl_high"),
    ("auto light", "headlights_auto"), ("auto beam", "headlights_auto"),
    ("dipped", "hl_low"), ("low beam", "hl_low"),
    ("headlights", "headlights_auto"),   # the on/off/auto toggle
    ("headlight", "hl_low"), ("head light", "hl_low"), ("headlamp", "hl_low"),
    ("side light", "position_lights"), ("position light", "position_lights"),
    ("park light", "position_lights"), ("parking light", "position_lights"),
    ("front fog", "fog_front"), ("rear fog", "fog_rear"), ("fog", "fog_front"),
    ("reverse light", "reverse"), ("beacon", "beacon"),
    ("interior light", "interior_light"), ("dome light", "interior_light"),
    ("dash bright", "dash_night"), ("panel bright", "dash_night"),
    ("hazard", "hazards"),
    ("turn", "turn"), ("indicator", "turn"), ("blinker", "turn"),
    # wipers / climate
    ("rear wiper", "rear_wiper"), ("rear washer", "rear_washer"),
    ("headlight wash", "headlight_washer"),
    ("intermittent wiper", "wiper_auto"), ("auto wiper", "wiper_auto"),
    ("washer", "washer"), ("wash", "washer"), ("wiper", "wiper"),
    ("rear defrost", "defrost_rear"), ("rear demist", "defrost_rear"),
    ("front defrost", "defrost_front"), ("defrost", "defrost_front"), ("demist", "defrost_front"),
    ("recirc", "recirc_on"), ("blower", "fan"), ("fan", "fan"),
    ("cabin temp", "temp_cabin"), ("ambient temp", "temp_ambient"),
    # engine / drivetrain
    ("ignition", "ignition"), ("key on", "ignition"),
    ("engine start", "engine_start"), ("starter", "engine_start"),
    ("engine crank", "engine_start"), ("crank", "engine_start"),
    ("glow plug", "preheat"), ("preheat", "preheat"),
    ("engine map", "engine_map"), ("map ", "engine_map"), ("mapping", "engine_map"),
    ("check engine", "check_engine"), ("mil", "check_engine"),
    ("engine warn", "engine_warning"), ("engine", "engine"),
    ("rpm", "rpm"), ("rev limit", "rpm"), ("torque", "torque"),
    ("air filter", "air_filter"), ("exhaust temp", "exhaust_temp"), ("exhaust", "exhaust"),
    # oil / battery / fuel / coolant
    ("oil temp", "oil_temp"), ("oil level", "oil_level"), ("oil", "oil"),
    ("battery", "battery"), ("charge", "charge"), ("alternator", "charge"),
    ("fuel low", "fuel_low"), ("low fuel", "fuel_low"), ("fuel", "fuel"),
    ("coolant", "coolant_temp"), ("water temp", "coolant_temp"),
    # brakes
    ("hand brake", "parking_brake"), ("handbrake", "parking_brake"),
    ("park brake", "parking_brake"), ("parking brake", "parking_brake"),
    ("brake bias", "tune"), ("bias", "tune"), ("brake balance", "tune"),
    ("brake mig", "tune"), ("brake migration", "tune"),
    ("anti-roll", "tune"), ("anti roll", "tune"), ("roll bar", "tune"),
    ("arb", "tune"), ("sway bar", "tune"),
    ("brake fluid", "brake_fluid"), ("brake warn", "brake_warning"),
    ("brake temp", "brake_warning"), ("retarder", "retarder"),
    ("abs", "abs"),
    # tyres / traction / stability
    ("tyre pressure", "tyre_pressure"), ("tire pressure", "tyre_pressure"),
    ("tyre temp", "tyre"), ("tyre", "tyre"), ("tire", "tyre"),
    ("traction control", "tc"), ("traction", "tc"), ("tc ", "tc"), ("tc+", "tc"), ("tc-", "tc"),
    ("stability", "esp"), ("esp off", "esp_off"), ("esp", "esp"),
    # transmission / steering / drive
    ("gearbox", "gearbox"), ("transmission", "gearbox"), ("shift up", "shift_up"),
    ("shift down", "shift_down"), ("upshift", "shift_up"), ("downshift", "shift_down"),
    ("steering", "steering"), ("4wd", "awd"), ("awd", "awd"), ("differential", "gearbox"),
    ("diff", "gearbox"), ("drs", "bolt"), ("wing", "bolt"), ("aero", "bolt"),
    ("ers", "charge"), ("energy", "charge"), ("boost", "charge"), ("push to pass", "charge"),
    # body / driver aids
    ("seat belt", "seatbelt"), ("seatbelt", "seatbelt"),
    ("seat heat", "seat_heat"),
    ("seat fore", "seat_fore"), ("seat forward", "seat_fore"), ("seat front", "seat_fore"),
    ("seat aft", "seat_aft"), ("seat back", "seat_recline"), ("seat rear", "seat_aft"),
    ("seat recline", "seat_recline"), ("backrest", "seat_recline"),
    ("seat up", "seat_up"), ("seat raise", "seat_up"), ("seat higher", "seat_up"),
    ("seat down", "seat_down"), ("seat lower", "seat_down"),
    ("seat", "seat"),
    ("bonnet", "hood"), ("hood", "hood"), ("boot", "trunk"), ("trunk", "trunk"),
    ("door", "door"), ("window", "window"), ("lock", "lock"),
    ("cruise", "cruise"), ("adaptive cruise", "adaptive_cruise"),
    ("lane assist", "lane_assist"), ("park assist", "park_assist"),
    ("hud", "hud"), ("gps", "gps"), ("airbag", "airbag"), ("horn", "horn"),
    ("pit limit", "speed"), ("pit speed", "speed"), ("pit", "flag"),
    ("warning", "warning"), ("alert", "alert"), ("info", "info"),
    # media / comms (Material)
    ("play", "media_play"), ("pause", "media_pause"), ("next track", "media_next"),
    ("prev track", "media_prev"), ("radio", "radio"),
    ("push to talk", "mic"), ("ptt", "mic"), ("voip", "mic"), ("mic", "mic"),
    ("chat", "chat"), ("message", "chat"),
    # non-car
    ("flag", "flag"), ("black flag", "flag"), ("blue flag", "flag"),
    ("mirror", "eye"), ("look ", "eye"), ("vr", "eye"), ("ipd", "eye"),
    ("clock", "timer"), ("lap time", "timer"), ("delta", "speed"),
]


def label_glyph(label: str) -> str | None:
    s = (label or "").lower()
    for needle, glyph in _LABEL_HINTS:
        if needle in s:
            return glyph
    return None
