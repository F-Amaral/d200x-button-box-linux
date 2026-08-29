"""Ulanzi D200 / D200x wire protocol -- only the parts a button box needs.

The framing and the input-report layout were reverse-engineered from USB
captures of Ulanzi Studio by earlier projects (strmdck, ulanzi-d200-linux,
companion-surface-d200); see README for provenance. This module implements the
INPUT path (key + knob events) and the brightness command. Image/label upload
to the LCD keys is deliberately out of scope for now.

Wire frame (both directions):

    offset  bytes  meaning
    0       2      0x7c 0x7c            header
    2       2      uint16 big-endian    command
    4       4      uint32 little-endian payload length
    8       N      payload

Input report payload (command 0x0101, or 0x0102 on some units / the D200x):

    payload[0]  state    (opaque; ignored)
    payload[1]  index    physical control id
    payload[2]  marker   0x02 => this is a rotary-encoder event
    payload[3]  action   0x00 release / 0x01 press / 0x02 turn-left / 0x03 turn-right

`index` values seen so far: 0..12 = the small LCD keys, 13 = the wide
status/clock key, 17/18/19 = the three rotary encoders. Confirm yours with
`d200x-button-box debug`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

VENDOR_ID = 0x2207
PRODUCT_ID = 0x0019
# Interface 0 carries this protocol. Interface 1 is a HID-keyboard emulation the
# device uses for its own standalone hotkeys -- not useful here, we skip it.
PROTOCOL_INTERFACE = 0

HEADER = b"\x7c\x7c"
PACKET_SIZE = 1024

CMD_SET_BUTTONS = 0x0001
CMD_SET_SMALL_WINDOW = 0x0006
CMD_SET_BRIGHTNESS = 0x000A
CMD_IN_BUTTON = 0x0101
CMD_IN_BUTTON_ALT = 0x0102  # observed on some units; treat identically
CMD_IN_DEVICE_INFO = 0x0303

KNOB_INDICES = (17, 18, 19)  # the three rotary encoders on the D200x
STATUS_KEY_INDEX = 13        # the wide clock / stats key
PAGE_KEY_INDICES = (15, 16)  # the two buttons flanking the encoders (left, right)

ACT_RELEASE = 0x00
ACT_PRESS = 0x01
ACT_TURN_LEFT = 0x02
ACT_TURN_RIGHT = 0x03

_KNOB_ACTION = {
    ACT_RELEASE: "release",
    ACT_PRESS: "press",
    ACT_TURN_LEFT: "left",
    ACT_TURN_RIGHT: "right",
}


@dataclass(frozen=True)
class InputEvent:
    index: int      # physical control id from the report
    kind: str       # "key" | "knob"
    action: str     # "press" | "release" | "left" | "right"
    raw: bytes      # payload[0:4], for the debug dump

    @property
    def name(self) -> str:
        if self.kind == "knob":
            return f"knob{self.index}"
        if self.index == STATUS_KEY_INDEX:
            return "status"
        if self.index in PAGE_KEY_INDICES:
            return "aux_l" if self.index == PAGE_KEY_INDICES[0] else "aux_r"
        return f"key{self.index}"


def frame_packets(cmd: int, payload: bytes) -> list[bytes]:
    """Split `payload` into 1024-byte wire packets.

    Packet 0 is `[7c 7c][cmd:BE16][len:LE32][first 1016 bytes]`; any further
    packets are raw 1024-byte chunks with no header. Caller prepends the 0x00
    HID report-ID byte per packet before writing.
    """
    head = bytearray(PACKET_SIZE)
    head[0:2] = HEADER
    struct.pack_into(">H", head, 2, cmd)
    struct.pack_into("<I", head, 4, len(payload))
    first = payload[: PACKET_SIZE - 8]
    head[8 : 8 + len(first)] = first
    packets = [bytes(head)]
    for off in range(PACKET_SIZE - 8, len(payload), PACKET_SIZE):
        packets.append(payload[off : off + PACKET_SIZE].ljust(PACKET_SIZE, b"\x00"))
    return packets


def build_brightness(percent: int) -> bytes:
    """A single 1024-byte SET_BRIGHTNESS packet. percent is clamped to 0..100."""
    percent = max(0, min(100, int(percent)))
    return frame_packets(CMD_SET_BRIGHTNESS, str(percent).encode("ascii"))[0]


def build_small_window(mode: int = 1, time_str: str = "") -> bytes:
    """SET_SMALL_WINDOW packet (`mode|cpu|mem|HH:MM:SS|gpu`).

    Sent every couple of seconds it doubles as the firmware watchdog / keep-alive
    that stops the deck falling back to its standalone screen. mode 1 = clock.
    """
    payload = f"{mode}|0|0|{time_str}|0".encode()
    return frame_packets(CMD_SET_SMALL_WINDOW, payload)[0]


def parse_input(data: bytes) -> InputEvent | None:
    """Parse one HID report. Returns None for anything that isn't a key/knob event."""
    if len(data) < 12 or data[0:2] != HEADER:
        return None
    cmd = struct.unpack_from(">H", data, 2)[0]
    if cmd not in (CMD_IN_BUTTON, CMD_IN_BUTTON_ALT):
        return None

    index, marker, act = data[9], data[10], data[11]
    payload = bytes(data[8:12])

    if index in KNOB_INDICES or marker == 0x02:
        return InputEvent(index, "knob", _KNOB_ACTION.get(act, "release"), payload)

    action = "press" if act == ACT_PRESS else "release"
    return InputEvent(index, "key", action, payload)
