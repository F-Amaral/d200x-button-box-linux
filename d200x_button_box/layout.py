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


def _draw_caption(d, text: str, font_name: str, colour, cw: int = ICON_SIZE, ch: int = ICON_SIZE) -> None:
    """A small single line of text in the lower whitespace (glyph + name).

    Leading/trailing decoration is dropped -- labels like ``-> LMU`` / ``→ Pit``
    become just the name.
    """
    text = re.sub(r"^[\s\W_]+|[\s\W_]+$", "", " ".join((text or "").split()))
    if not text:
        return
    max_w = cw - 18
    font = _text_font(font_name, 30)
    if d.textlength(text, font=font) > max_w:
        while len(text) > 1 and d.textlength(text + "…", font=font) > max_w:
            text = text[:-1].rstrip()
        text += "…"
    w = d.textlength(text, font=font)
    asc, desc = font.getmetrics()
    d.text(((cw - w) / 2, ch - 20 - asc - desc), text, font=font, fill=colour)


def render_icon(style: dict | None, text: str = "", glyph: str | None = None,
                caption: str = "", size: tuple[int, int] | None = None) -> bytes:
    """RGBA PNG, ``size`` (w, h) or 196x196.

    - a real ISO tell-tale (no frame -- the symbol IS the icon), OR
    - a Material glyph / text initials on a circle / rounded-square frame.

    ``caption`` is a short label drawn small along the bottom, under a glyph or
    tell-tale, so e.g. a profile-switch key shows both the icon and the target
    name. Ignored when the icon is itself text (initials). A non-square ``size``
    (the wide status key) always uses the rounded-square frame.
    """
    Image, ImageDraw, _ = _pil()
    s = merge_style(style)
    W, H = size or (ICON_SIZE, ICON_SIZE)
    m = min(W, H)
    cap = " ".join((caption or "").split())

    if glyph and telltales.has(glyph):
        scale = 0.66 if cap else 0.86
        base = telltales.tint(glyph, s["fg"], int(m * scale))
        if not cap and (W, H) == (ICON_SIZE, ICON_SIZE):
            return _pad_png(base, m)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        with Image.open(io.BytesIO(base)) as sym:
            sym = sym.convert("RGBA")
            img.alpha_composite(sym, ((W - sym.size[0]) // 2, 4 if cap else (H - sym.size[1]) // 2))
        if cap:
            _draw_caption(ImageDraw.Draw(img), cap, s["font"], s["fg"], W, H)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad, bw, rad = 8, 12, 34
    box = (pad, pad, W - pad - 1, H - pad - 1)
    fill = None if s["mode"] == "ring" else s["fill"]
    if s["shape"] == "round" or W != H:
        d.rounded_rectangle(box, rad, fill=fill, outline=s["border"], width=bw)
    else:
        d.ellipse(box, fill=fill, outline=s["border"], width=bw)

    if glyph and (cp := glyphs.codepoint(glyph)) is not None:
        font = _glyph_font(round(m * (0.45 if cap else 0.57)))
        ch = chr(cp)
        tb = d.textbbox((0, 0), ch, font=font)
        dy = -round(m * 0.12) if cap else 0
        d.text(((W - (tb[2] - tb[0])) / 2 - tb[0], (H - (tb[3] - tb[1])) / 2 - tb[1] + dy),
               ch, font=font, fill=s["fg"])
        if cap:
            _draw_caption(d, cap, s["font"], s["fg"], W, H)
    else:
        t = icon_initials(text)
        if t:
            font = _text_font(s["font"], round(m * {1: 0.62, 2: 0.48, 3: 0.37}.get(len(t), 0.3)))
            tb = d.textbbox((0, 0), t, font=font)
            d.text(((W - (tb[2] - tb[0])) / 2 - tb[0], (H - (tb[3] - tb[1])) / 2 - tb[1]),
                   t, font=font, fill=s["fg"])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pad_png(png: bytes, w: int, h: int | None = None) -> bytes:
    """Centre `png` on a transparent canvas (no scaling)."""
    Image = _pil()[0]
    h = w if h is None else h
    with Image.open(io.BytesIO(png)) as im:
        im = im.convert("RGBA")
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.paste(im, ((w - im.size[0]) // 2, (h - im.size[1]) // 2), im)
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return buf.getvalue()


# the wide status key ("small window" slot 3_2) is 458 x 196
STATUS_W, STATUS_H = 458, 196


def _load_icon_png(path: str, size: tuple[int, int] | None = None) -> bytes | None:
    Image = _pil()[0]
    dims = size or (ICON_SIZE, ICON_SIZE)
    try:
        with Image.open(path) as img:
            img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
            if img.size != dims:
                img = img.resize(dims, Image.Resampling.LANCZOS)
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
                     game_base: dict, nav_base: dict,
                     size: tuple[int, int] | None = None) -> bytes | None:
    binding = binding or {}

    box = is_box_binding(binding)
    base = nav_base if box else merge_style(game_base, page_style)
    style = merge_style(base, binding.get("icon_style"))

    from . import widgets
    if widgets.is_widget(binding):
        try:
            # widgets are neutral by default (a clock isn't a "sim control")
            wstyle = merge_style(nav_base, page_style, binding.get("icon_style"))
            return widgets.render(binding, size, wstyle)
        except Exception as e:  # noqa: BLE001 - a bad widget must not break the push
            log.warning("widget %s: %s", binding.get("widget"), e)
            return None

    if binding.get("icon"):
        png = _load_icon_png(binding["icon"], size)
        if png:
            return png

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
        # an unlabeled controller key: show its button number, dimmed, so the
        # deck isn't a black square and you can see what to bind in-game
        if isinstance(binding.get("gamepad"), int):
            dim = merge_style(style, {"mode": "ring", "fg": "#5b6675"})
            return render_icon(dim, text=str(binding["gamepad"]), size=size)
        return None
    try:
        return render_icon(style, text=text, glyph=glyph, caption=caption, size=size)
    except Exception as e:  # noqa: BLE001 - a font/Pillow hiccup must not break the push
        log.warning("icon render failed (%s / %s): %s", glyph, text, e)
        return None


def build_manifest(icons: dict[int, bytes], orientation: int = 0,
                   indices: list[int] | None = None) -> tuple[bytes, dict[str, bytes]]:
    from . import orient

    manifest: dict[str, dict] = {}
    files: dict[str, bytes] = {}
    for index in (indices if indices is not None else _MANIFEST_INDICES):   # logical indices
        view: dict = {"Font": _FONT}
        if icons.get(index):
            name = f"Images/{hashlib.md5(icons[index]).hexdigest()}.png"
            files[name] = icons[index]
            view["Icon"] = name
        entry: dict = {"State": 0, "ViewParam": [view]}
        if index == protocol.STATUS_KEY_INDEX:
            entry["SmallViewMode"] = 2   # the firmware clock / readout overlay
        manifest[_cell(orient.to_physical(index, orientation))] = entry
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


def _cell_icon(page, index, game_base, nav_base) -> bytes | None:
    """One cell's icon before rotation. Handles the wide status slot's modes."""
    binding = page.keys.get(index, {}) if page is not None else {}
    if index == protocol.STATUS_KEY_INDEX:
        from . import widgets
        smode = binding.get("status") or ("load" if binding.get("clock") is False else "clock")
        # clock / load -> the firmware fills the strip; off / widget -> our own wide icon
        if smode == "off" or widgets.is_widget(binding):
            return resolve_key_icon(binding, page.style, game_base, nav_base,
                                    size=(STATUS_W, STATUS_H))
        return None
    return resolve_key_icon(binding, page.style, game_base, nav_base)


def build_set_buttons(page=None, icon_cfg: dict | None = None, orientation: int = 0,
                      only: set[int] | None = None) -> bytes:
    """`page` is a config.Page (or None for a blank layout); `icon_cfg` is
    settings.icon (`{game: {...}, nav: {...}}`); `orientation` is how the deck is
    mounted (0 or 180). `only` restricts the manifest to those cells -- a
    **partial** update (`CMD_PARTIAL_UPDATE`), which re-renders just those cells
    without blanking the deck."""
    from . import orient

    icon_cfg = icon_cfg or {}
    game_base = merge_style(DEFAULT_GAME_STYLE, icon_cfg.get("game"))
    nav_base = merge_style(DEFAULT_NAV_STYLE, icon_cfg.get("nav"))
    indices = [i for i in _MANIFEST_INDICES if only is None or i in only]

    icons: dict[int, bytes] = {}
    if page is not None:
        for index in indices:
            png = _cell_icon(page, index, game_base, nav_base)
            if png:
                icons[index] = png

    deg = orient.icon_degrees(orientation)
    if deg:
        icons = {i: orient.rotate_png(p, deg) for i, p in icons.items()}
    manifest, files = build_manifest(icons, orientation, indices)
    payload = _archive(manifest, files, b"")
    tries = 0
    while not _payload_safe(payload) and tries < 64:
        tries += 1
        payload = _archive(manifest, files, os.urandom(8 * tries).hex().encode())
    return payload


def render_cell(page, index: int, icon_cfg: dict | None = None, orientation: int = 0) -> bytes | None:
    """One cell's final (rotated) icon -- for the widget change-check."""
    from . import orient

    icon_cfg = icon_cfg or {}
    png = _cell_icon(page, index,
                     merge_style(DEFAULT_GAME_STYLE, icon_cfg.get("game")),
                     merge_style(DEFAULT_NAV_STYLE, icon_cfg.get("nav")))
    return orient.rotate_png(png, orient.icon_degrees(orientation)) if png else None


def widget_cells(page) -> list[int]:
    """Manifest indices on `page` that carry a `widget:` (daemon ticks these)."""
    from . import widgets

    if page is None:
        return []
    return [i for i in _MANIFEST_INDICES if widgets.is_widget(page.keys.get(i))]
