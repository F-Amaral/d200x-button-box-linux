# Hardware notes

Everything here was learned by reverse-engineering the device and reading prior
community work (see Credits). None of it is official.

## The device

- USB id **`2207:0019`** ("Zkswe ulanzi" / Fuzhou Rockchip).
- Controls: 13 small LCD keys (`key0`–`key12`), 1 wide status key (`status`,
  index 13), 2 round aux buttons flanking the encoders (`aux_l` = 15,
  `aux_r` = 16), 3 rotary encoders with click (`knob17`–`knob19`).
- Two HID interfaces:
  - **interface 0** — the deck protocol (input reports + display uploads). This
    is what the daemon reads.
  - **interface 1** — a real HID keyboard the device drives itself. Keys
    programmed in Ulanzi Studio (including the factory demo macros) are typed
    straight from firmware. The daemon `EVIOCGRAB`s these evdev nodes so they
    don't reach the desktop.

## Why we read `/dev/hidrawN` directly

The `hidapi` PyPI wheel ships the libusb backend. On this hardware it opens
interface 0 but never delivers the interrupt-IN reports (it throws
`read error`). Reading the kernel `hidraw` node ourselves is a few lines and
just works. Writes get a `0x00` report-ID byte prepended.

## Wire protocol (input path)

Frame, both directions:

```
offset  bytes  meaning
0       2      0x7c 0x7c            header
2       2      uint16 big-endian    command
4       4      uint32 little-endian payload length
8       N      payload
```

Input report — command `0x0101` (or `0x0102` on some units):

```
payload[0]  state    (opaque; ignored)
payload[1]  index    control id (see above)
payload[2]  marker   0x02 => rotary-encoder event
payload[3]  action   0x00 release / 0x01 press / 0x02 turn-left / 0x03 turn-right
```

Full command set (all reverse-engineered by the community projects in Credits;
`strmdck` + `companion-surface-d200` cover it):

| cmd | direction | payload | what |
|--|--|--|--|
| `0x0001` | out | zip (`manifest.json` + `Images/*.png`) | SET_BUTTONS — the whole layout; **blanks every screen** while it re-renders |
| `0x000d` | out | same zip, **only the changed cells** | PARTIALLY_UPDATE_BUTTONS — re-renders just those cells, no blank. Needs a prior `0x0001`. |
| `0x0006` | out | `mode\|cpu\|mem\|HH:MM:SS\|gpu\|24H\|suffix` | SET_SMALL_WINDOW — the wide `3_2` strip (see below) |
| `0x000a` | out | ascii int | SET_BRIGHTNESS |
| `0x000b` | out | JSON `{Align,Color,FontName,ShowTitle,Size,Weight}` | SET_LABEL_STYLE — global manifest font (we bake it per-key instead) |
| `0x000f` | out | empty | LOCKSCREEN — blank + ignore input until unlocked |
| `0x0010` | out | empty | UNLOCKSCREEN |
| `0x0101` / `0x0102` | in | `state\|index\|marker\|action` | key / encoder event |
| `0x0303` | in | ascii string | device info (firmware / serial) |
| `0x010b` | in | — | ack for a write; ignored |

On the **D200X** the `3_2` slot is a normal (wide) button — `SmallViewMode: 2`
only tells the firmware to allocate the full 458px width; a partial `0x000d` to
that cell just replaces its icon.

### The wide status key ("small window", slot `3_2`, 458×196)

SET_SMALL_WINDOW's first field is a mode that picks what the strip shows:

| mode | shows |
|--|--|
| `0` | CPU / RAM / GPU stats |
| `1` | analogue dial clock |
| `2` | **BACKGROUND** — the icon set for slot `3_2` in the manifest |
| `200`–`203` | digital date/time/weekday variants |

The payload is 7 fields: `mode|cpu|mem|HH:MM:SS|gpu|24H|suffix` (older captures
show only the first five; the D200X seems to want all seven). The mode byte,
not the manifest, drives the display; the manifest needs `SmallViewMode: 2` on
`3_2` so the firmware allocates the full 458px width. A custom status icon =
`SmallViewMode: 2` + a 458×196 Icon on `3_2`, then SET_SMALL_WINDOW mode `2`
sent **once** (the D200X doesn't run the clock keep-alive; the daemon keeps the
deck awake with a periodic SET_BRIGHTNESS instead). Learned from
`jcalado/companion-surface-d200` and `Tyaaa-aa/Ulanzi-Deck-Linux`.

## Firmware quirks

- **Silent until handshake.** Interface 0 reports nothing until the device
  receives a SET_BUTTONS upload — that switches it from standalone-keyboard mode
  to host mode. The daemon sends one on start and on every profile/page change.
- **Drifts back to standalone.** Without a write every couple of seconds the
  deck shows a colour-circle animation, stops reporting, and may re-enumerate on
  USB. The daemon sends SET_SMALL_WINDOW every `heartbeat_seconds` — it both
  keeps the deck in host mode and sets the status strip (mode 1 clock / mode 0
  load / mode 2 the key's own icon).
- **Encoder click on release only.** Holding an encoder button sends nothing;
  press+release arrive together when you let go. A knob click can't be a hold —
  the daemon fires it as a `pulse_ms` pulse.
- **SET_BUTTONS zip bug.** The first byte of every raw 1024-byte chunk after the
  first must not be `0x00` or `0x7c`; the payload builder retries with a random
  dummy file until safe.
- **USB enumeration.** Some hubs/ports fail to bring up both HID interfaces. A
  USB 2.0 hub, or a USB 2.0 port straight off the motherboard, is the known fix.

## Credits

Protocol reverse-engineered by
[strmdck](https://github.com/redphx/strmdck),
[racerxdl/ulanzi-d200-linux](https://github.com/racerxdl/ulanzi-d200-linux),
[Tyaaa-aa/Ulanzi-Deck-Linux](https://github.com/Tyaaa-aa/Ulanzi-Deck-Linux) and
[jcalado/companion-surface-d200](https://github.com/jcalado/companion-surface-d200)
(the control-index map and the SET_BUTTONS-before-input behaviour come from the
last one). This project adds the gamepad output, profiles/pages, and the
sim-racing focus.
