# Configuration

Everything lives in `~/.config/d200x-button-box/`:

```
settings.yaml            device / gamepad / api / active profile / auto-detect / home
profiles/<name>.yaml     one or more pages of bindings for one context
```

`d200x-button-box init` creates it with `settings.yaml` and the profiles
`default`, `lmu`, `ac_evo`, `launcher`. Set `D200X_CONFIG_DIR` to use a
different location. Set `D200X_NO_DEVICE=1` to run the daemon API-only, never
opening the hardware — for working on the web UI on a spare `api.port` without
disturbing the real daemon.

The generated profiles use a **stable** control → gamepad-button map, so it's
safe to re-generate without breaking bindings you already made in a game:

| control | button |
|--|--|
| LCD keys 0–12 | 1–13 |
| wide status key | 14 |
| aux L / aux R | home / page (buttons 15–16 reserved, unused) |
| encoder 17 turn L / turn R / click | 17 / 18 / 19 |
| encoder 18 | 20 / 21 / 22 |
| encoder 19 | 23 / 24 / 25 |

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

games:                     # install folders, for "import labels from a game"
  lmu: /path/to/Le Mans Ultimate   # auto-filled from Steam libraries if found

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

An optional top-level `game:` field links the profile to a game (set by "Import
from a game"; editable via the 🎮 chip under the deck). It drives the editor's
bind-to-game tool. Deleting the active profile is allowed — the deck falls back
to the home profile; only the home profile itself can't be deleted.

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
- `icon: /path/to.png` — an uploaded image (auto-resized to 196×196)
- `icon_text: "PIT"` — override the auto initials on a generated icon
- `icon_style: {…}` — per-key overrides of the page style (below)

## Key icons

Every LCD key with a label gets an icon so the deck never shows bare text on
black. Resolution order: an uploaded `icon:` image → otherwise a **generated**
one (initials of `icon_text` or `label` on a shape).

Generated-icon style is a merge of the built-in defaults, the page's `style`,
and the key's `icon_style`:

```yaml
# a page with its own default look
style: {mode: ring, shape: circle, border: "#4a9eff", fill: "#1b1f26", fg: "#ffffff", font: sans}
keys:
  0: {gamepad: 1, label: "Pit", icon_text: "PIT"}
  1: {gamepad: 2, label: "Radio", icon_style: {mode: solid, fill: "#c0392b"}}
```

- `mode`: `solid` (filled) or `ring` (outline only, dark centre)
- `shape`: `circle` or `round`
- `border` / `fill` / `fg`: hex colours
- `font`: `sans` / `condensed` / `mono` / `liberation` (text mode only)

A key can also carry `glyph: <name>` — a real **ISO 7000 automotive tell-tale**
(`hl_low`, `hl_high`, `turn`, `hazards`, `wiper`, `washer`, `horn`, `fan`,
`battery`, `oil`, `tc`, `abs`, `esp`, …), a **composed** icon (`engine_start`,
`seat_fore`/`seat_aft`/`seat_up`/`seat_down`/`seat_recline`), or a **Material
Icons** name; `GET /api/glyphs` lists them all. Tell-tales and composed icons
are drawn frameless; everything else sits on the circle / rounded-square frame.

Composed icons (`engine_start`, the `seat_*` family) are generated: a spec in
`d200x_button_box/compose.py` (`COMPOSED`) describes a base ISO symbol + drawn
arrows / arcs / lines (coords as fractions of the icon square), and
`tools/build-composed-icons.py` renders each to a committed PNG in
`assets/telltales/`. To add or change one, edit `COMPOSED` and re-run the tool.

### Adjusting an icon by hand

The web UI's **Icons** button (or **customise `<glyph>`** on a key) opens a
visual editor: pick a base, nudge scale / position, add arrow / arc / line /
tick layers, live preview. **＋** makes a brand-new icon (seeded from the one
open); on the CLI, `d200x-button-box icons new <name> [--base <telltale>]`.
Each layer can take an optional **`color:`** so it draws in a fixed colour
instead of following the key's icon colour. A **`region`** layer recolours /
fills part of the symbol clipped to a rect or ellipse — `color:` repaints the
strokes there, `fill:` floods their enclosed interior and the strokes are drawn
back on top (base `turn` + a region over the left half = a blue arrow with a
white centre). **Save** stores your spec in
`~/.config/d200x-button-box/icons.yaml` and renders it to
`~/.config/d200x-button-box/generated/<name>.png`, which then shadows the
bundled default. **Reset to built-in** removes your override.

Maintainers propagating a tweak upstream: get it right in the editor, then
`d200x-button-box icons promote <name>` bakes the spec into
`assets/composed.yaml` + the committed `assets/telltales/<name>.png` and clears
your override. Commit both. The **spec (JSON)** view in the editor shows the
current spec for copy/paste.

```python
# a spec
"seat_up": {
    "base": "seat", "base_scale": 0.54, "base_at": [0.40, 0.44],
    "layers": [
        {"type": "line",  "from": [0.06, 0.9], "to": [0.8, 0.9], "w": 0.045},
        {"type": "arrow", "at": [0.86, 0.86], "dir": "up", "len": 0.34, "head": 0.12, "w": 0.055},
    ],
}
```

**Nav keys pick a glyph automatically:** `{page: next}` → chevron,
`{profile: home}` → house, `{command: …}` → terminal. **Game keys** with a label
but no glyph get one from keywords — car-control words map to the tell-tales —
and fall back to the label's initials.

To pin an icon to a control label (used by every key with that label, across
profiles), use the **set / change** link in the editor's Auto look, or
`d200x-button-box icons action "Cycle Lights" headlights_auto`
(`--clear` to undo). Stored in `~/.config/d200x-button-box/action_icons.yaml`.

## Two style baselines

`settings.icon` has `game` and `nav` sub-styles:

```yaml
icon:
  game: {mode: solid, shape: circle, border: "#4a9eff", fill: "#2a3140", fg: "#ffffff"}
  nav:  {mode: ring,  shape: round,  border: "#7d8794", fill: "#0d0f13", fg: "#aeb6c2"}
```

Action keys use `game` (then `page.style`, then the key's `icon_style`);
navigation keys (`page:` / `profile:` bindings, or `role: nav`) use `nav`. The
visual language: **circle = a sim control, rounded square = a box control.**

## Page navigation

```yaml
# settings.yaml
nav: {prev_key: 15, next_key: 16}   # default: the two aux buttons
hold_ms: 500
```

The aux buttons page prev / next with **no binding needed**. On a multi-page
profile the left one is `tap → prev page`, `hold → home` (`settings.home`); on a
single-page profile it's just `home`. Put an explicit binding on those keys in a
profile to override. `+ page` in the web UI moves any explicit aux bindings onto
the new page.

Any binding can take `hold:` for a second press-and-hold action:

```yaml
0: {gamepad: 1, hold: {command: "some-reset-script"}}
```

In the web UI: the **⚙** next to the page tabs edits the page style + name; the
**style** button in a key's editor sets a per-key override; **upload an image**
for a real picture. Uploaded images that no profile references any more are
cleaned from `icons/` automatically.

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

## Import a profile from a game

"Import from a game" in the web UI (or `POST /api/profiles/<name>/import`)
reads the game's own control config and builds a deck profile *for that game*:
every deck key bound to the **D200x Button Box** controller in the game gets
that in-game control name as its `label`.

- If no profile named after the game exists yet, it is **created** from the
  stable gamepad-button map, and `settings.games` / `auto_detect` are seeded so
  the daemon switches to it when the game runs.
- If one exists, the panel offers **Update it** or **New profile `<game>-2`**.
- **Le Mans Ultimate** — reads `UserData/player/direct input.json` (`games.lmu`,
  auto-detected from Steam libraries).
- **Assetto Corsa Rally** — reads the UE5 SaveGame
  `…/compatdata/<appid>/pfx/…/AppData/Local/acr/Saved/SaveGames/EnhancedInputUserSettings.sav`
  (auto-located). Read-only for now (no bind-to-game yet).
- **Assetto Corsa EVO** — reads `…/compatdata/3058630/pfx/…/Saved Games/ACE/
  input_devices.inputdeviceconfiguration` (a protobuf). Handles plain and
  bipolar (cycle +/-) bindings. Read-only. Unrecognised in-game controls still
  label the button as `control <n>`.
- Buttons bound in-game that aren't on any deck control are listed in the
  import report so you can assign them.
- `overwrite: false` keeps labels you typed by hand (only matters when updating).

## Bind-to-game (the reverse)

For a profile linked to a game that supports writing (**LMU**, **AC Rally**),
the key editor shows a "bind this button in &lt;game&gt;" dropdown under a
`gamepad` binding — pick a control, apply, and the game's own config is updated
(a one-time `.d200x-bak` backup is written next to it).

- **Close the game first** — both read their config at startup and rewrite it on
  exit. The daemon refuses the write while the game process is detected running.
- LMU: writes `Input[control] = {device, id}` in `direct input.json`. Bind any
  one control to the deck inside LMU once first, so the game has recorded the
  device GUID.
- AC Rally: splices the HardwareKey in the active key profile inside
  `EnhancedInputUserSettings.sav` (a UE5 GVAS save). Binding a button to a
  control also clears whatever else was on that button.

## The home button

`init` maps the leftmost aux button (the round one, no screen) to home. Press it
mid-race to pop to the launcher; after `revert_seconds` with no deck input it
returns you to the game's profile automatically. Any deck press resets the
timer; choosing a profile explicitly cancels it. Set `home.key: null` to
disable, or point it at any control index.
