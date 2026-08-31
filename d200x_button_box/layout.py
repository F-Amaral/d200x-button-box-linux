"""Build the SET_BUTTONS payload, and render key icons.

The D200x does not report key/knob events on interface 0 until it receives a
SET_BUTTONS upload -- that switches it from standalone-keyboard mode to
host-controlled mode. So the daemon sends one on startup and on every
profile/page change.

Every LCD key gets an icon so the deck is never bare text on black:

    binding.icon              an uploaded image, wins
    binding.glyph             an explicit Material Icons glyph name
    action / label glyph      auto: {page:}/{profile:}/{command:} and label hints
    binding.icon_text / label initials, drawn in the shape
    (nothing)

Style is layered: a baseline (settings.icon.game for action keys, .nav for
navigation keys) <- page.style <- binding.icon_style.

Firmware bug: the first byte of every raw 1024-byte chunk after the first must
not be 0x00 or 0x7c; we retry the archive with a random dummy file until safe.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import zipfile

from . import glyphs, protocol, telltales

log = logging.getLogger(__name__)

ICON_SIZE = 196

_FONT = {  # the manifest's own text style -- unused now (icons carry the text)
    "Align": "bottom", "Color": 0xFFFFFF, "FontName": "Roboto",
    "ShowTitle": False, "Size": 10, "Weight": 80,
}

_MANIFEST_INDICES = [*range(13), protocol.STATUS_KEY_INDEX]

DEFAULT_GAME_STYLE = {"mode": "solid", "shape": "circle", "fill": "#2a3140",
                      "border": "#4a9eff", "fg": "#ffffff", "font": "sans"}
DEFAULT_NAV_STYLE = {"mode": "ring", "shape": "round", "fill": "#0d0f13",
                     "border": "#7d8794", "fg": "#aeb6c2", "font": "sans"}
STYLE_KEYS = ("mode", "shape", "fill", "border", "fg", "font")

_TEXT_FONT_FILES = {
    "sans": ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf"],
    "condensed": ["DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "mono": ["DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf"],
    "liberation": ["LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
}


def _cell(index: int) -> str:
    return f"{index % 5}_{index // 5}"


def merge_style(*layers) -> dict:
    out = dict(DEFAULT_GAME_STYLE)
    for layer in layers:
        for k in STYLE_KEYS:
            if layer and layer.get(k) not in (None, ""):
                out[k] = layer[k]
    return out


def icon_initials(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    if len(words) >= 2:
        return "".join(w[0] for w in words[:3]).upper()
    return (words[0][:3] if words else "").upper()


def _pil():
    from PIL import Image, ImageDraw, ImageFont

    return Image, ImageDraw, ImageFont


def _text_font(name: str, size: int):
    _, _, ImageFont = _pil()
    for cand in _TEXT_FONT_FILES.get(name, _TEXT_FONT_FILES["sans"]):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _glyph_font(size: int):
    _, _, ImageFont = _pil()
    return ImageFont.truetype(str(glyphs.FONT_PATH), size)


def _draw_caption(d, text: str, font_name: str, colour) -> None:
    """A small single line of text in the lower whitespace (glyph + name).

    Leading/trailing decoration is dropped -- labels like ``-> LMU`` / ``→ Pit``
    become just the name.
    """
    text = re.sub(r"^[\s\W_]+|[\s\W_]+$", "", " ".join((text or "").split()))
    if not text:
        return
    S, max_w = ICON_SIZE, ICON_SIZE - 18
    font = _text_font(font_name, 30)
    if d.textlength(text, font=font) > max_w:
        while len(text) > 1 and d.textlength(text + "…", font=font) > max_w:
            text = text[:-1].rstrip()
        text += "…"
    w = d.textlength(text, font=font)
    asc, desc = font.getmetrics()
    d.text(((S - w) / 2, S - 20 - asc - desc), text, font=font, fill=colour)


def render_icon(style: dict | None, text: str = "", glyph: str | None = None,
                caption: str = "") -> bytes:
    """196x196 RGBA PNG.

    - a real ISO tell-tale (no frame -- the symbol IS the icon), OR
    - a Material glyph / text initials on a circle / rounded-square frame.

    ``caption`` is a short label drawn small along the bottom, under a glyph or
    tell-tale, so e.g. a profile-switch key shows both the icon and the target
    name. Ignored when the icon is itself text (initials).
    """
    Image, ImageDraw, _ = _pil()
    s = merge_style(style)
    S = ICON_SIZE
    cap = " ".join((caption or "").split())

    if glyph and telltales.has(glyph):
        scale = 0.66 if cap else 0.86
        base = telltales.tint(glyph, s["fg"], int(S * scale))
        if not cap:
            return _pad_png(base, S)
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        with Image.open(io.BytesIO(base)) as sym:
            sym = sym.convert("RGBA")
            img.alpha_composite(sym, ((S - sym.size[0]) // 2, 4))
        d = ImageDraw.Draw(img)
        _draw_caption(d, cap, s["font"], s["fg"])
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad, bw, rad = 8, 12, 34
    box = (pad, pad, S - pad - 1, S - pad - 1)
    fill = None if s["mode"] == "ring" else s["fill"]
    if s["shape"] == "round":
        d.rounded_rectangle(box, rad, fill=fill, outline=s["border"], width=bw)
    else:
        d.ellipse(box, fill=fill, outline=s["border"], width=bw)

    if glyph and (cp := glyphs.codepoint(glyph)) is not None:
        font = _glyph_font(88 if cap else 112)
        ch = chr(cp)
        tb = d.textbbox((0, 0), ch, font=font)
        dy = -24 if cap else 0
        d.text(((S - (tb[2] - tb[0])) / 2 - tb[0], (S - (tb[3] - tb[1])) / 2 - tb[1] + dy),
               ch, font=font, fill=s["fg"])
        if cap:
            _draw_caption(d, cap, s["font"], s["fg"])
    else:
        t = icon_initials(text)
        if t:
            font = _text_font(s["font"], {1: 122, 2: 94, 3: 72}.get(len(t), 58))
            tb = d.textbbox((0, 0), t, font=font)
            d.text(((S - (tb[2] - tb[0])) / 2 - tb[0], (S - (tb[3] - tb[1])) / 2 - tb[1]),
                   t, font=font, fill=s["fg"])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pad_png(png: bytes, size: int) -> bytes:
    Image = _pil()[0]
    with Image.open(io.BytesIO(png)) as im:
        im = im.convert("RGBA")
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(im, ((size - im.size[0]) // 2, (size - im.size[1]) // 2), im)
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return buf.getvalue()


def _load_icon_png(path: str) -> bytes | None:
    Image = _pil()[0]
    try:
        with Image.open(path) as img:
            img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
            if img.size != (ICON_SIZE, ICON_SIZE):
                img = img.resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except (OSError, ValueError) as e:
        log.warning("icon %s: %s", path, e)
        return None


def is_nav_binding(binding: dict) -> bool:
    if not isinstance(binding, dict):
        return False
    if binding.get("role") == "nav":
        return True
    return "page" in binding or "profile" in binding


def is_box_binding(binding: dict) -> bool:
    """A 'box control' — nav / page / profile / shell command / raw keystroke.
    Gets the neutral (nav) icon baseline; gamepad + empty keys are 'sim'."""
    return is_nav_binding(binding) or "command" in binding or "key" in binding


def resolve_key_icon(binding: dict, page_style: dict | None,
                     game_base: dict, nav_base: dict) -> bytes | None:
    binding = binding or {}
    if binding.get("icon"):
        png = _load_icon_png(binding["icon"])
        if png:
            return png

    box = is_box_binding(binding)
    base = nav_base if box else merge_style(game_base, page_style)
    style = merge_style(base, binding.get("icon_style"))

    # explicit wins: a chosen glyph, else chosen letters, else derive one.
    # a glyph the user picked (or one implied by the action, e.g. a profile
    # switch) carries the label along as a small caption; a glyph the label
    # itself matched does not (that would just repeat the label).
    label = binding.get("label", "")
    glyph, caption = binding.get("glyph"), ""
    if glyph:
        caption = label
    elif not binding.get("icon_text"):
        glyph = glyphs.action_glyph(binding)
        if glyph:
            caption = label
        elif not is_nav_binding(binding):
            glyph = glyphs.label_glyph(label)
    text = binding.get("icon_text") or label or ""
    if not glyph and not text:
        return None
    try:
        return render_icon(style, text=text, glyph=glyph, caption=caption)
    except Exception as e:  # noqa: BLE001 - a font/Pillow hiccup must not break the push
        log.warning("icon render failed (%s / %s): %s", glyph, text, e)
        return None


def build_manifest(icons: dict[int, bytes]) -> tuple[bytes, dict[str, bytes]]:
    manifest: dict[str, dict] = {}
    files: dict[str, bytes] = {}
    for index in _MANIFEST_INDICES:
        view: dict = {"Font": _FONT}
        if icons.get(index):
            name = f"Images/{hashlib.md5(icons[index]).hexdigest()}.png"
            files[name] = icons[index]
            view["Icon"] = name
        entry: dict = {"State": 0, "ViewParam": [view]}
        if index == protocol.STATUS_KEY_INDEX:
            entry["SmallViewMode"] = 2
        manifest[_cell(index)] = entry
    return json.dumps(manifest).encode(), files


def _archive(manifest: bytes, files: dict[str, bytes], dummy: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        z.writestr("manifest.json", manifest)
        for name, data in files.items():
            z.writestr(name, data)
        if dummy:
            z.writestr("dummy.txt", dummy)
    return buf.getvalue()


def _payload_safe(payload: bytes) -> bool:
    for i in range(protocol.PACKET_SIZE - 8, len(payload), protocol.PACKET_SIZE):
        if payload[i] in (0x00, 0x7C):
            return False
    return True


def build_set_buttons(page=None, icon_cfg: dict | None = None) -> bytes:
    """`page` is a config.Page (or None for a blank layout); `icon_cfg` is
    settings.icon (`{game: {...}, nav: {...}}`)."""
    icon_cfg = icon_cfg or {}
    game_base = merge_style(DEFAULT_GAME_STYLE, icon_cfg.get("game"))
    nav_base = merge_style(DEFAULT_NAV_STYLE, icon_cfg.get("nav"))

    icons: dict[int, bytes] = {}
    if page is not None:
        for index in _MANIFEST_INDICES:
            binding = page.keys.get(index, {})
            if index == protocol.STATUS_KEY_INDEX:
                png = _load_icon_png(binding["icon"]) if binding.get("icon") else None
            else:
                png = resolve_key_icon(binding, page.style, game_base, nav_base)
            if png:
                icons[index] = png

    manifest, files = build_manifest(icons)
    payload = _archive(manifest, files, b"")
    tries = 0
    while not _payload_safe(payload) and tries < 64:
        tries += 1
        payload = _archive(manifest, files, os.urandom(8 * tries).hex().encode())
    return payload
