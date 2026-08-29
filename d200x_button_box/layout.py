"""Build the SET_BUTTONS payload.

The D200x does not report key/knob events on interface 0 until it receives a
SET_BUTTONS upload -- that is what switches it from standalone-keyboard mode to
host-controlled mode. So the daemon sends one on startup (and re-sends on
profile changes). Text labels and per-key icons are included.

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


def _cell(index: int) -> str:
    return f"{index % 5}_{index // 5}"


def _load_icon_png(path: str) -> bytes | None:
    """Return a 196x196 PNG for `path`, or None if it can't be read."""
    try:
        from PIL import Image
    except ImportError:
        log.warning("Pillow not installed -- icons skipped, labels only")
        return None
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


def build_manifest(labels: dict[int, str], icons: dict[int, bytes]) -> tuple[bytes, dict[str, bytes]]:
    manifest: dict[str, dict] = {}
    files: dict[str, bytes] = {}
    for index in _MANIFEST_INDICES:
        view: dict = {"Font": _FONT}
        if labels.get(index):
            view["Text"] = labels[index]
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
) -> bytes:
    icons = {}
    for idx, path in (icon_paths or {}).items():
        png = _load_icon_png(path)
        if png:
            icons[idx] = png
    manifest, files = build_manifest(labels or {}, icons)
    payload = _archive(manifest, files, b"")
    tries = 0
    while not _payload_safe(payload) and tries < 64:
        tries += 1
        payload = _archive(manifest, files, os.urandom(8 * tries).hex().encode())
    return payload
