# Configuration

Everything lives in `~/.config/d200x-button-box/`:

```
settings.yaml            device / gamepad / api / active profile / auto-detect / home
profiles/<name>.yaml     one or more pages of bindings for one context
```

`d200x-button-box init` creates it with `settings.yaml` and the profiles
`default`, `lmu`, `ac_evo`, `launcher`.

Editing `settings.yaml` or the **active** profile file takes effect within a
second — no restart. The daemon reloads and the deck re-renders.

## settings.yaml

```yaml
device:
  brightness: 80            # 0-100, null to leave alone
  heartbeat_seconds: 2      # watchdog write interval that keeps the deck in host
                            # mode; do not set to 0 or the deck drops out
  grab_keyboard: true       # swallow the deck's own firmware HID keyboard

gamepad:
  name: D200x Button Box
  buttons: 32               # size of the virtual pad; raise if you map more

pulse_ms: 60               # how long a knob step / momentary press is held

active_profile: launcher   # used when nothing else selects a profile

auto_detect:               # profile -> case-insensitive substrings in /proc/*/cmdline
  lmu: [LeMansUltimate]
  ac_evo: [AssettoCorsaEVO, acevo]

home:
  key: 15                  # control index that acts as "home" in every profile; null = off
  profile: launcher        # where it jumps to
  revert_seconds: 5        # idle seconds before returning to auto-detect; 0 = stay

api:
  host: 127.0.0.1          # 0.0.0.0 to reach it from the LAN (phone)
  port: 8377
  token: null              # require this token when set (phase 2)
```

## Profile selection

The daemon picks a profile in this order:

1. manual override — `d200x-buttonboxd --profile X`, a `{profile:}` binding, or
   the API
2. `auto_detect` — first profile whose substrings match a running process
3. `active_profile` in settings

A `{profile: "auto"}` binding clears a manual override.

## Profiles and pages

A profile is one or more **pages**. Single-page profiles are flat:

```yaml
keys:
  0: {gamepad: 1, label: "TURN L"}
knobs:
  17: {left: {gamepad: 17}, right: {gamepad: 18}, press: {gamepad: 19}}
```

Multi-page — 13 keys × N. A page switch releases held buttons and re-renders:

```yaml
pages:
  - name: drive
    keys:
      0: {gamepad: 1, label: "TURN L"}
      16: {page: "next"}          # rightmost aux cycles pages
  - name: pit / radio
    keys:
      0: {gamepad: 20, label: "BOX BOX"}
      16: {page: "next"}
```

Switching profiles resets to page 0.

## Bindings

Each key/knob-event binding has exactly one action:

| form | effect |
|--|--|
| `{gamepad: N}` | hold virtual joystick button `N` while the key is down |
| `{gamepad: N, momentary: true}` | short `pulse_ms` press instead of a hold |
| `{key: "F8"}` | send a keystroke via `ydotool` / `xdotool` |
| `{command: "sh -c ..."}` | run a shell command |
| `{profile: "lmu"}` | switch profile — also `home`, `auto`, `next`, `prev` |
| `{page: "next"}` | switch page — also `prev` or a page number |

Plus optional, for the LCD key:

- `label: "PIT"` — text on the key
- `icon: /path/to.png` — image, auto-resized to 196×196

Knobs take `left` / `right` / `press`, each a binding:

```yaml
knobs:
  17:
    left:  {gamepad: 17}
    right: {gamepad: 18}
    press: {gamepad: 19}
```

Encoder turns fire one pulse per detent. The encoder **click is reported only on
release** by the firmware, so it is always a pulse — see
[hardware.md](hardware.md).

## The launcher profile

`launcher` is the default `active_profile` — what's on the deck when no game is
running. Use `{command:}` to start LMU/CrewChief and `{profile:}` to jump into a
game profile:

```yaml
keys:
  0: {label: "LMU + VR", command: "steam steam://rungameid/2399420"}
  1: {label: "CrewChief", command: "sh -c 'cd ~/CrewChiefV4 && ./CrewChief.sh &'"}
  2: {label: "-> LMU", profile: "lmu"}
```

When you launch a game, `auto_detect` switches to its profile on its own; on
quit it falls back to `launcher`.

## The home button

`init` maps the leftmost aux button (the round one, no screen) to home. Press it
mid-race to pop to the launcher; after `revert_seconds` with no deck input it
returns you to the game's profile automatically. Any deck press resets the
timer; choosing a profile explicitly cancels it. Set `home.key: null` to
disable, or point it at any control index.
