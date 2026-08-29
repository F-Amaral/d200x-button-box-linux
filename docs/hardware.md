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

Commands the daemon sends: `0x0001` SET_BUTTONS (a zip: `manifest.json` +
`Images/*.png`), `0x0006` SET_SMALL_WINDOW (`mode|cpu|mem|HH:MM:SS|gpu`),
`0x000a` SET_BRIGHTNESS. Device replies with a `0x010b` ack.

## Firmware quirks

- **Silent until handshake.** Interface 0 reports nothing until the device
  receives a SET_BUTTONS upload — that switches it from standalone-keyboard mode
  to host mode. The daemon sends one on start and on every profile/page change.
- **Drifts back to standalone.** Without a write every couple of seconds the
  deck shows a colour-circle animation, stops reporting, and may re-enumerate on
  USB. The daemon's `heartbeat_seconds` (SET_SMALL_WINDOW every 2s) prevents it;
  it also puts a clock on the wide status key.
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
