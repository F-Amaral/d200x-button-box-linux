"""Build the SET_BUTTONS payload, and render key icons.

The D200x does not report key/knob events on interface 0 until it receives a
SET_BUTTONS upload -- that switches it from standalone-keyboard mode to
host-controlled mode. So the daemon sends one on startup and on every
profile/page change.

Every LCD key with a label gets an icon: an uploaded image if `icon:` points to
one, otherwise a generated one (initials in a circle / rounded square) using the
page's `style` merged with the key's own `icon_style`. That way the deck never
shows bare text on black.

Payload structure, mirrored from Ulanzi Studio USB captures (via the
companion-surface-d200 project):

    manifest.json     at archive root -- {"<col>_<row>": {State, ViewParam:[...]}}
    Images/<id>.png   196x196 icons referenced from the manifest

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

from . import protocol

log = logging.getLogger(__name__)

ICON_SIZE = 196

_FONT = {
    "Align": "bottom",
    "Color": 0xFFFFFF,
    "FontName": "Source Han Sans SC",
    "ShowTitle": True,
    "Size": 10,
    "Weight": 80,
}

# LCD grid keys the manifest must describe: 0..12 plus the wide status slot.
_MANIFEST_INDICES = [*range(13), protocol.STATUS_KEY_INDEX]

# --- generated-icon style -------------------------------------------------
DEFAULT_STYLE = {
    "mode": "solid",      # "solid" (filled) | "ring" (just an outline, dark centre)
    "shape": "circle",    # "circle" | "round" (rounded square)
    "fill": "#1b1f26",
    "border": "#4a9eff",
    "fg": "#ffffff",
    "font": "sans",       # sans | condensed | mono | liberation
}
STYLE_KEYS = tuple(DEFAULT_STYLE)

_FONT_FILES = {
    "sans": ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf"],
    "condensed": ["DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "mono": ["DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf"],
    "liberation": ["LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
}


def _cell(index: int) -> str:
    return f"{index % 5}_{index // 5}"


def merge_style(*layers: dict | None) -> dict:
    out = dict(DEFAULT_STYLE)
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


def _font(name: str, size: int):
    _, _, ImageFont = _pil()
    for cand in _FONT_FILES.get(name, _FONT_FILES["sans"]):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_icon(style: dict | None, text: str) -> bytes:
    """A 196x196 RGBA PNG: initials of `text` on a circle / rounded square."""
    Image, ImageDraw, _ = _pil()
    s = merge_style(style)
    S = ICON_SIZE
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad, bw, rad = 8, 12, 32
    box = (pad, pad, S - pad - 1, S - pad - 1)
    fill = None if s["mode"] == "ring" else s["fill"]
    if s["shape"] == "round":
        d.rounded_rectangle(box, rad, fill=fill, outline=s["border"], width=bw)
    else:
        d.ellipse(box, fill=fill, outline=s["border"], width=bw)

    t = icon_initials(text)
    if t:
        n = len(t)
        font = _font(s["font"], {1: 122, 2: 94, 3: 72}.get(n, 58))
        tb = d.textbbox((0, 0), t, font=font)
        d.text(((S - (tb[2] - tb[0])) / 2 - tb[0], (S - (tb[3] - tb[1])) / 2 - tb[1]),
               t, font=font, fill=s["fg"])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _load_icon_png(path: str) -> bytes | None:
    """A 196x196 PNG for an uploaded image `path`, or None if unreadable."""
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


def resolve_icon(label: str, icon_path: str | None, icon_text: str | None,
                 icon_style: dict | None, page_style: dict | None) -> bytes | None:
    """Uploaded image if `icon_path` is set, else a generated one if there's text."""
    if icon_path:
        png = _load_icon_png(icon_path)
        if png:
            return png
    text = (icon_text or label or "").strip()
    if not text:
        return None
    try:
        return render_icon(merge_style(page_style, icon_style), text)
    except Exception as e:  # noqa: BLE001 - a font/Pillow hiccup must not break the push
        log.warning("icon render for %r failed: %s", text, e)
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
            entry["SmallViewMode"] = 2  # gives the wide slot its full width
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


def build_set_buttons(
    labels: dict[int, str] | None = None,
    icon_paths: dict[int, str] | None = None,
    icon_texts: dict[int, str] | None = None,
    icon_styles: dict[int, dict] | None = None,
    page_style: dict | None = None,
) -> bytes:
    labels = labels or {}
    icon_paths = icon_paths or {}
    icon_texts = icon_texts or {}
    icon_styles = icon_styles or {}

    icons: dict[int, bytes] = {}
    for index in _MANIFEST_INDICES:
        # the wide status key shows the clock (heartbeat); only an explicit
        # uploaded image goes there, never a generated one
        label = "" if index == protocol.STATUS_KEY_INDEX else labels.get(index, "")
        png = resolve_icon(label, icon_paths.get(index),
                           icon_texts.get(index) if index != protocol.STATUS_KEY_INDEX else None,
                           icon_styles.get(index), page_style)
        if png:
            icons[index] = png

    manifest, files = build_manifest(icons)
    payload = _archive(manifest, files, b"")
    tries = 0
    while not _payload_safe(payload) and tries < 64:
        tries += 1
        payload = _archive(manifest, files, os.urandom(8 * tries).hex().encode())
    return payload
