"""Build the SET_BUTTONS payload.

The D200x does not report key/knob events on interface 0 until it receives a
SET_BUTTONS upload -- that is what switches it from standalone-keyboard mode to
host-controlled mode. So the daemon sends one on startup. We include text
labels (handy in VR); icons are a later job.

Payload structure, mirrored from Ulanzi Studio USB captures (via the
companion-surface-d200 project):

    manifest.json     at archive root -- {"<col>_<row>": {State, ViewParam:[...]}}
    Images/<id>.png   icons (not used here)

Firmware bug: the first byte of every raw 1024-byte chunk after the first must
not be 0x00 or 0x7c; we retry the archive with a random dummy file until safe.
A label-only payload is small enough to fit one packet, so this rarely trips.
"""

from __future__ import annotations

import io
import json
import os
import zipfile

from . import protocol

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


def build_manifest(labels: dict[int, str]) -> bytes:
    manifest: dict[str, dict] = {}
    for index in _MANIFEST_INDICES:
        view: dict = {"Font": _FONT}
        if labels.get(index):
            view["Text"] = labels[index]
        entry: dict = {"State": 0, "ViewParam": [view]}
        if index == protocol.STATUS_KEY_INDEX:
            entry["SmallViewMode"] = 2  # gives the wide slot its full width
        manifest[_cell(index)] = entry
    return json.dumps(manifest).encode()


def _archive(manifest: bytes, dummy: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        z.writestr("manifest.json", manifest)
        if dummy:
            z.writestr("dummy.txt", dummy)
    return buf.getvalue()


def _payload_safe(payload: bytes) -> bool:
    for i in range(protocol.PACKET_SIZE - 8, len(payload), protocol.PACKET_SIZE):
        if payload[i] in (0x00, 0x7C):
            return False
    return True


def build_set_buttons(labels: dict[int, str] | None = None) -> bytes:
    manifest = build_manifest(labels or {})
    payload = _archive(manifest, b"")
    tries = 0
    while not _payload_safe(payload) and tries < 64:
        tries += 1
        payload = _archive(manifest, os.urandom(8 * tries).hex().encode())
    return payload
