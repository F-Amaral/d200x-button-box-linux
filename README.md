# d200x-button-box

Use an **Ulanzi Stream Controller D200x** (13 LCD keys + 1 wide status key + 3
rotary encoders) as an **auxiliary button box for sim racing on Linux** — aimed
at *Le Mans Ultimate* first, *Assetto Corsa EVO* second, both running through
Proton/Wine.

The daemon reads the deck's USB-HID input reports and re-emits every key and
knob as a button on a **virtual gamepad** (`uinput`). Games — native or Proton —
see an ordinary `/dev/input/js*` controller and let you bind each button in
their normal controller settings. No keystroke injection required, so it works
while the game is focused *and* while you're deep in a VR headset.

Keystroke output (`ydotool`/`xdotool`) and "run a shell command" are available
per-binding too, for things like CrewChief toggles.

## Why this exists

The D200x has **no native Linux support**. Existing community projects
([racerxdl/ulanzi-d200-linux](https://github.com/racerxdl/ulanzi-d200-linux),
[Tyaaa-aa/Ulanzi-Deck-Linux](https://github.com/Tyaaa-aa/Ulanzi-Deck-Linux),
[jcalado/companion-surface-d200](https://github.com/jcalado/companion-surface-d200))
are stream-deck managers: OBS scenes, app launchers, media keys. They inject
input with **xdotool (X11 only)** and none of them expose a joystick. That's the
wrong shape for a sim rig on Wayland + Proton + VR. This project reuses their
**reverse-engineered wire protocol** (see `d200x_button_box/protocol.py` for
provenance) and does one thing: deck → gamepad.

## Hardware notes

- USB id is **`2207:0019`**.
- It presents **two HID interfaces**: interface 0 is the deck protocol (this is
  what we read); interface 1 is a **real HID keyboard** the device drives
  itself. Any key you program in Ulanzi Studio as a keyboard shortcut is sent on
  interface 1 straight from firmware — it works on Linux with no software at all
  (see "Two ways to use it").
- We read `/dev/hidrawN` directly — **no hidapi / libusb**. The hidapi wheel's
  libusb backend opens interface 0 but never delivers its input reports on this
  hardware.
- If some USB ports enumerate the deck but `enum` shows no hidraw node, try a
  USB 2.0 port straight off the motherboard.
- Control indices are confirmed on a real D200x (see "First run"). No Ulanzi
  Studio needed: the daemon sends the layout handshake itself and grabs the
  firmware keyboard so the factory macros never reach the desktop.

## Install

```bash
cd ~/Projetos/d200x-button-box
python -m venv .venv && . .venv/bin/activate
pip install -e .

# device + uinput permissions
sudo cp udev/70-d200x.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger --attr-match=idVendor=2207
echo uinput | sudo tee /etc/modules-load.d/uinput.conf
sudo modprobe uinput
# then PHYSICALLY unplug/replug the deck -- uaccess is not applied to a
# device that is already connected.
```

Then unplug/replug the deck. Log out/in once if `uinput` still says permission
denied, or add yourself to the `input` group.

Optional, only if you use `{key: ...}` bindings on Wayland:

```bash
sudo pacman -S ydotool && systemctl --user enable --now ydotool
```

## First run — sanity check

```bash
d200x-button-box debug
```

`debug` uploads a blank layout (the LCD keys go dark — that is the deck
entering host mode) and then prints one line per report:

```
18:58:18  7c 7c 01 01 f6 03 00 00 01 00 01 01 ...   ->  key0 press
18:58:47  7c 7c 01 01 f6 03 00 00 01 11 02 03 ...   ->  knob17 right
```

Control indices confirmed on a real D200x: `key0`–`key12` the LCD grid,
`status` the wide key, `aux_l` / `aux_r` the two buttons flanking the encoders,
`knob17`–`knob19` the encoders (turn + click). If yours differ, adjust the
`keys:` / `knobs:` indices in the config.

## Configure

```bash
d200x-button-box gen-config          # writes ~/.config/d200x-button-box/config.yaml
```

The starter file maps every control (16 keys + 3 knobs × turn/turn/click) to
sequential gamepad buttons. Edit bindings:

```yaml
keys:
  0: {gamepad: 1}                     # LCD key 0 -> joystick button 1
  1: {gamepad: 2, label: "PIT"}       # print "PIT" on that LCD key
  2: {key: "F8"}                      # send a keystroke instead of a button
  3: {command: "sh -c 'echo radio | socat - ...'"}
  4: {gamepad: 5, momentary: true}    # short pulse instead of hold (toggles)

knobs:
  17:
    left:  {gamepad: 17}              # turns always fire as a short pulse
    right: {gamepad: 18}
    press: {gamepad: 19}              # drives both the press and release edge
```

## Run

```bash
d200x-button-box run                  # foreground, logs each input
# or as a service:
cp systemd/d200x-button-box.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now d200x-button-box
```

Check it with `evtest` or `jstest /dev/input/js0` — you should see
"D200x Button Box" and its buttons firing.

## Bind in the games

- **Le Mans Ultimate**: needs Proton-GE (JacKeTUs' fork) for the `d2d1` fix.
  In-game *Options → Controls*, pick a function, click assign, press the deck
  key. LMU binds per-device so the deck coexists with the Moza GS V2.
  Good candidates for an auxiliary box: turn signals, headlights, wiper,
  pit request / pit menu nav, MFD pages, brake-bias +/- and TC +/- on the
  knobs, push-to-talk / VoIP, CrewChief.
- **Assetto Corsa EVO**: recent Proton or Proton-GE. *Settings → Controls*,
  assign the same way. Its axis "Is Slider" auto-detect only affects analog
  axes, not these buttons.

## VR / focused-game note

Because output is a gamepad, not synthetic keypresses, bindings fire regardless
of window focus and never collide with the game's keyboard mappings — which is
what you want with the Quest 3 on and the mouse busy in LMU.

## Known firmware quirks

- **The encoder click is reported only on release** — the deck sends nothing
  while it's held, then press+release together when you let go. So a knob click
  is always a momentary tap; it can't be a hold. The daemon fires it as a
  `pulse_ms` pulse. Bind a key or a turn if you need hold semantics.
- **The deck falls back to its standalone screen** (a colour-circle animation,
  and it stops reporting) unless something writes to it every couple of seconds.
  The daemon does this via `heartbeat_seconds` (SET_SMALL_WINDOW, default 2s),
  which also puts a clock on the wide status key.

## Status & roadmap

**Working, verified on a real D200x:** every control → virtual gamepad /
keystroke / command; the SET_BUTTONS handshake + 2s heartbeat that keep
interface 0 reporting; grabbing the firmware keyboard so factory macros don't
leak; text labels on the LCD keys; brightness; YAML config; `debug` dump;
systemd unit. `pytest -q` covers the parser, payload builder, and event routing.

**Not yet:** icons on the keys (only text today); per-key state/colour. The ZIP
path already carries icons — a `layout.py` extension, not new protocol work.

## Credits

Wire protocol reverse-engineered by
[strmdck](https://github.com/redphx/strmdck),
[racerxdl/ulanzi-d200-linux](https://github.com/racerxdl/ulanzi-d200-linux),
[Tyaaa-aa/Ulanzi-Deck-Linux](https://github.com/Tyaaa-aa/Ulanzi-Deck-Linux) and
[jcalado/companion-surface-d200](https://github.com/jcalado/companion-surface-d200).
This project only adds the gamepad output and the sim-racing focus. MIT.
