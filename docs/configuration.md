# Configuration

All config lives in `~/.config/d200x-button-box/`:

```
settings.yaml          device, gamepad, API, profile selection, navigation
profiles/<name>.yaml   one or more pages of bindings for one context
```

`d200x-button-box init` creates the folder with a `settings.yaml` and the
starter profiles `default`, `lmu`, `ac`, `launcher`.

Two environment variables help when developing:

- `D200X_CONFIG_DIR` — use a different config folder.
- `D200X_NO_DEVICE=1` — run the daemon API-only, never opening the hardware.
  Handy for working on the web UI on a spare `api.port` alongside the real one.

Edits to `settings.yaml` or the **active** profile take effect within a second —
the daemon reloads and the deck re-renders. No restart.

## The stable button map

Every deck control sends a fixed gamepad button. The map never changes, so you
can regenerate profiles or re-run `init` without breaking bindings you already
made in a game:

| control | button |
|--|--|
| LCD keys 0–12 | 1–13 |
| wide status key | 14 |
| aux L / aux R | 15 / 16 (reserved; the aux buttons are navigation by default) |
| encoder 17 — turn left / turn right / click | 17 / 18 / 19 |
| encoder 18 | 20 / 21 / 22 |
| encoder 19 | 23 / 24 / 25 |

On a multi-page profile the LCD keys shift by 13 per page (page 2 → buttons
14–26) so pages don't reuse each other's buttons.

## settings.yaml

```yaml
device:
  brightness: 80           # 0-100, or null to leave it alone
  heartbeat_seconds: 2     # watchdog write that keeps the deck awake; never 0
  grab_keyboard: true      # swallow the deck's own firmware keyboard
  orientation: 0           # 0 or 180 — how the deck is mounted (see below)
  idle_sleep_seconds: 60   # dark the screens after this idle; any key — or a
                           # running (auto-detected) game — wakes it (0 = never)

gamepad:
  name: D200x Button Box
  buttons: 32              # size of the virtual pad; raise if you map more

pulse_ms: 60              # how long a knob step / momentary press is held
hold_ms: 500             # press time that counts as a hold, not a tap

active_profile: launcher  # used when nothing else selects a profile

auto_detect:              # profile -> case-insensitive substrings in /proc/*/cmdline
  lmu: [Le Mans Ultimate]   # a substring of the running exe / its Steam folder
  ac: [acs.exe]
  ac_rally: [acr.exe, Assetto Corsa Rally]

games:                    # game -> install folder, for import / bind-to-game
  lmu: /path/to/Le Mans Ultimate   # auto-filled from your Steam libraries

nav:                      # what the aux buttons do (see "Navigation")
  binds:
    15: {tap: prev_page, hold: home}
    16: {tap: next_page}

home:
  profile: launcher       # where the "home" function jumps to
  revert_seconds: 5       # idle seconds before auto-detect takes over again; 0 = stay

api:
  host: 127.0.0.1         # 0.0.0.0 to reach it from the LAN (a phone)
  port: 8377
  token: null             # when set, every /api/* call must send it; open the
                          # web UI once as  http://<ip>:8377/?token=<token>
```

## Profile selection

The daemon picks a profile in this order:

1. **Manual override** — `d200x-buttonboxd --profile X`, a `{profile: X}`
   binding, or the API. A `{profile: auto}` binding clears it.
2. **Auto-detect** — the first profile whose `auto_detect` substrings match a
   running process.
3. **`active_profile`** in `settings.yaml`.

## Mounting orientation

`device.orientation` (`0` or `180`, also in Settings → Device → Mounting) is for
mounting the deck upside down in a rig. At `180` the whole deck works
"as mounted": the 13 LCD keys reverse, the two aux buttons swap, the encoders
reverse, and every icon is turned 180°. You configure keys, pages and
navigation exactly as you see them — key 0 is the top-left key from where you
sit.

Encoder turn direction is unchanged (spinning the device in its own plane keeps
clockwise clockwise). The wide status strip is a fixed firmware element: it
physically stays bottom-right, so at `180` it appears at your top-left, and its
icon rotates but the firmware clock/load **text** can't — use status mode `off`
with a custom icon if that bothers you. 90° / 270° aren't supported (the wide
strip can't fit a portrait grid).

## Profiles and pages

A profile is one or more **pages**. A single-page profile is flat:

```yaml
keys:
  0: {gamepad: 1, label: "TURN L"}
knobs:
  17: {left: {gamepad: 17}, right: {gamepad: 18}, press: {gamepad: 19}}
```

Multi-page — 13 keys each. Switching page releases any held buttons and
re-renders:

```yaml
pages:
  - name: drive
    keys:
      0: {gamepad: 1, label: "TURN L"}
      16: {page: next}          # rightmost aux cycles pages
  - name: pit / radio
    keys:
      0: {gamepad: 20, label: "BOX BOX"}
      16: {page: next}
```

Switching profiles always resets to page 0.

An optional top-level `game:` links the profile to a game. It is set by "Import
from a game" and drives the editor's bind-to-game tool; edit it via the 🎮 chip
under the deck. Deleting the active profile is fine — the deck falls back to the
home profile. Only the home profile itself can't be deleted.

## Bindings

Each key or knob-event binding has exactly one action:

| form | effect |
|--|--|
| `{gamepad: N}` | hold virtual button `N` while the key is down |
| `{gamepad: N, momentary: true}` | a short `pulse_ms` press instead of a hold |
| `{key: "F8"}` | send a keystroke (via `ydotool` / `xdotool`) |
| `{command: "sh -c ..."}` | run a shell command |
| `{profile: "lmu"}` | switch profile — also `home`, `auto`, `next`, `prev` |
| `{page: next}` | switch page — also `prev` or a page number |

Any binding can carry a `hold:` for a second press-and-hold action:

```yaml
0: {gamepad: 1, hold: {command: "some-reset-script"}}
```

An LCD key can also take `label:` and icon fields — see **Key icons**.

## Navigation

The two round aux buttons are navigation by default, no binding needed.
`settings.nav.binds` maps a control index to `{tap: ..., hold: ...}`, where each
value is `prev_page`, `next_page` or `home`:

```yaml
nav:
  binds:
    15: {tap: prev_page, hold: home}   # aux L
    16: {tap: next_page}               # aux R
```

Put an explicit binding on an aux key in a profile to override navigation there.
`+ page` in the web UI moves any explicit aux bindings onto the new page.

**Home** pops the deck to `home.profile` (the launcher) mid-race. After
`home.revert_seconds` with no deck input it returns to the game's profile on its
own; any deck press resets that timer, and choosing a profile explicitly cancels
it. `revert_seconds: 0` stays put.

## Knobs

Each encoder takes `left` / `right` / `press`, each a full binding:

```yaml
knobs:
  17:
    left:  {gamepad: 17}
    right: {gamepad: 18}
    press: {gamepad: 19}
```

Encoder turns fire one `pulse_ms` pulse per detent. The firmware only reports an
encoder **click on release**, so a click is always a pulse, never a hold — see
[hardware.md](hardware.md).

## Widgets (live cells)

A `widget:` on a key is drawn by the daemon and refreshed in place — no
firmware clock/stat overlay, so it rotates with `device.orientation` like any
icon. It overrides the key's normal look; a `gamepad:`/`command:` on the same
key still works when pressed.

```yaml
keys:
  13: {widget: clock}                                 # replaces the firmware status clock
  3:  {widget: sysload}                               # CPU · RAM bars
  4:  {widget: shell, cmd: "sensors ...", interval: 5, unit: "°C"}
```

| kind | shows | refresh |
|--|--|--|
| `clock` | `HH:MM` | on the minute |
| `sysload` | CPU / RAM bars (red ≥ 90 %) | 2 s |
| `shell` | first stdout line of `cmd` + `unit` | `interval` seconds (default 5) |

Set `icon_style` for colours/font. On the wide status key, pick "Clock —
rendered" / "System load — rendered" in the editor. `mpris` / per-sim telemetry
widgets are planned (see plans/icon-system.md).

## Key icons

Every LCD key with a label gets an icon, so the deck never shows bare text on
black. Resolution order:

1. an uploaded `icon:` image (any PNG/JPG, auto-resized to 196×196), or
2. a **generated** icon — a glyph, or the initials of `icon_text` / `label`, on
   a shape.

Per-key fields:

- `label: "PIT"` — text on the key
- `icon: /path/to.png` — an uploaded image
- `icon_text: "PIT"` — override the auto initials
- `glyph: turn` — draw a named symbol instead of initials (below)
- `icon_style: {...}` — per-key style overrides

### Style

A generated icon's style is the merge of the built-in default, the page's
`style:`, and the key's `icon_style:`:

```yaml
style: {mode: ring, shape: circle, border: "#4a9eff", fill: "#1b1f26", fg: "#ffffff", font: sans}
keys:
  0: {gamepad: 1, label: "Pit", icon_text: "PIT"}
  1: {gamepad: 2, label: "Radio", icon_style: {mode: solid, fill: "#c0392b"}}
```

- `mode`: `solid` (filled) or `ring` (outline, dark centre)
- `shape`: `circle` or `round` (rounded square)
- `border` / `fill` / `fg`: hex colours
- `font`: `sans` / `condensed` / `mono` / `liberation` (text only)

`settings.icon` holds two baselines, `game` and `nav`. Action keys use `game`
(then the page style, then `icon_style`); navigation keys use `nav`. The visual
language is **circle = a sim control, rounded square = a box control**:

```yaml
icon:
  game: {mode: solid, shape: circle, border: "#4a9eff", fill: "#2a3140", fg: "#ffffff"}
  nav:  {mode: ring,  shape: round,  border: "#7d8794", fill: "#0d0f13", fg: "#aeb6c2"}
```

### Glyphs

`glyph:` can name:

- an **ISO 7000 automotive tell-tale** — `hl_low`, `hl_high`, `turn`, `hazards`,
  `wiper`, `washer`, `horn`, `fan`, `battery`, `oil`, `tc`, `abs`, `esp`, …
- a **composed** icon — `engine_start`, the `seat_*` family
- a **Material Icons** name

`GET /api/glyphs` lists them all. Tell-tales and composed icons are drawn
frameless; everything else sits on the frame.

Nav keys pick a glyph automatically (`{page: next}` → chevron, `{profile: home}`
→ house, `{command: ...}` → terminal). Game keys with a label but no glyph get
one from keywords (car-control words map to tell-tales), falling back to the
label's initials.

To pin a glyph to a control label — every key with that label, in every profile
— use the **set / change** link in the editor's Auto look, or:

```bash
d200x-button-box icons action "Cycle Lights" headlights_auto   # --clear to undo
```

### The icon editor

The web UI's **Icons** button (or **customise `<glyph>`** on a key) opens a
visual editor: pick a base symbol, nudge its scale and position, add
arrow / arc / line / tick layers, preview live. **＋** starts a brand-new icon;
on the CLI, `d200x-button-box icons new <name> [--base <telltale>]`.

- A layer can take a `color:` to draw in a fixed colour instead of the key's
  icon colour.
- A `region:` layer recolours or fills part of the symbol, clipped to a rect or
  ellipse. `color:` repaints the strokes there; `fill:` floods their enclosed
  interior and redraws the strokes on top (base `turn` + a region over the left
  half = a blue arrow with a white centre).

**Save** writes your spec to `icons.yaml` and renders
`generated/<name>.png`, which then shadows the bundled default. **Reset to
built-in** removes the override.

Maintainers propagating a tweak upstream: get it right in the editor, then
`d200x-button-box icons promote <name>` bakes the spec into `assets/` and clears
your override — commit both files.

## Games: import and bind-to-game

Both features read (or write) the game's own controller config. **Close the
game first** — each reads its config at startup, and the daemon refuses to write
while the game process is running. A one-time `.d200x-bak` backup is written
next to the file the first time it's changed.

| Game | Import | Bind-to-game | Config file |
|--|:--:|:--:|--|
| Le Mans Ultimate | ✅ | ✅ | `UserData/player/direct input.json` |
| Assetto Corsa | ✅ | ✅ | `…/Documents/Assetto Corsa/cfg/controls.ini` |
| Assetto Corsa Rally | ✅ | ✅ | `…/Saved/SaveGames/EnhancedInputUserSettings.sav` |
| Assetto Corsa EVO | ✅ | ✅ | `…/Saved Games/ACE/input_devices.inputdeviceconfiguration` (still validating) |

Install folders (and the save/config files under `compatdata/`) are located
from your Steam libraries automatically and stored in `settings.games`.

**Assetto Corsa** (and AC Rally / LMU) need the deck registered once: bind any
single control to it in the game's own controls menu first, so the game records
the device. AC's `controls.ini` covers Content Manager / CSP actions too
(`__EXT_*` / `__CM_*`). Button numbers are 0-based in the file, so `BUTTON =
your gamepad button − 1`.

### Import from a game

"Import from a game" in the web UI (or `POST /api/profiles/<name>/import`) reads
the game's config and labels each deck key that's bound to the **D200x Button
Box** controller with its in-game control name.

- If no profile named after the game exists yet, one is **created**: the full
  stable button map, unlabeled, with the game's control names layered on. Every
  key still sends its button, so you can bind any of them in-game right away.
  `settings.games` / `auto_detect` are seeded so the daemon switches to the
  profile when the game runs.
- If one exists, you get **Update it** or **New profile `<game>-2`**.
- In-game buttons that don't land on any deck control are listed in the import
  report so you can assign them.
- `overwrite: false` keeps labels you typed by hand (only matters on an update).

While the linked game is running, the daemon also **fills in labels live** — a
control you bind to the deck in-game shows up on the deck (name + auto icon)
within a few seconds, without a manual import. It only fills blank keys; it
never changes a label you set.

For AC EVO, bipolar "cycle" controls import as two entries (`… +` / `… -`).

### Bind-to-game

For a profile linked to a game, the key editor shows a **bind this button in
`<game>`** dropdown under a `gamepad` binding. Pick a control and the game's
config is updated the moment you pick it. Binding a control to a button also
clears whatever else was on it.

- **LMU** needs the device recorded once: bind any single control to the deck
  inside LMU before the first write, so the game has stored the device GUID.
- Dragging a key onto another in the web UI moves its in-game binding too.
- **AC EVO** exposes every control the game knows — the named ones plus every id
  that has a default keyboard binding, shown as `control <id>` until named.
  Names are **learned**: bind a `control <id>` to a deck key, give the key a
  label, and while AC EVO is running the daemon remembers that label for the
  control (in `game_names.yaml`) — the dropdown and imports then show the real
  name. `tools/acevo-probe.py` binds all the unnamed ids to spare buttons at
  once so you can name them from the in-game controls menu in a single pass.

## The launcher profile

`launcher` is the default `active_profile` — what's on the deck when no game is
running. Use `{command:}` to start a game or CrewChief and `{profile:}` to jump
into a game profile:

```yaml
keys:
  0: {label: "LMU + VR", command: "steam steam://rungameid/2399420"}
  1: {label: "CrewChief", command: "sh -c 'cd ~/CrewChiefV4 && ./CrewChief.sh &'"}
  2: {label: "-> LMU", profile: "lmu"}
  3: {label: "-> AC", profile: "ac"}
  4: {label: "Auto", profile: "auto"}
```

When a game starts, `auto_detect` switches to its profile on its own; on quit
the deck falls back to `launcher`.
