# Icon system — design notes

Where the generated-icon work is heading. Not all implemented yet.

## Principle: the deck is self-documenting in VR

You glance down mid-corner and must instantly know: *this row is car stuff,
these two are page nav, that corner is home.* Icons exist to make the deck
readable at a glance, not to be pretty.

## Three visual registers

| register | what | look |
|--|--|--|
| **game action** | headlights, TC, pit, radio — "what this does in the sim" | text initials in a **solid circle**, page accent colour. The current generator. |
| **deck / meta** | next/prev page, home, switch profile, back, launcher | a **glyph** (arrow, house, layers) in a **ring / rounded-square**, neutral colour. Visually *not* a car control. |
| **widget** | live value — gear, fuel %, lap delta, CPU temp | big number / bar / gauge, threshold-coloured, usually no border. (backlog) |

The shape/mode/colour split is the language: **circle = sim, square = box
control.** Consistent, pre-attentive.

## Icon resolution order (per key)

1. `icon:` — an uploaded image
2. `glyph:` — an explicit built-in glyph name
3. **auto-glyph from the action** — `{page: next}` → `chevron-right`,
   `{page: prev}` → `chevron-left`, `{profile: home}` → `house`,
   `{profile: auto}` → `refresh`, `{profile: <name>}` → `layers`,
   `{command: …}` → `terminal`. Nav keys "just work" with zero config.
4. `icon_text` / `label` initials — the generator
5. nothing

Auto-glyph keys also default to the **meta** look (ring, neutral) unless
overridden, so they read as box controls automatically.

## Glyph set — two sources

1. **Automotive tell-tales** — ~108 real dashboard symbols (mostly ISO 7000,
   all public domain), bundled as white-on-transparent PNGs in
   `assets/telltales/`, tinted to the icon colour at render time
   (`telltales.py`, pure Pillow). Source: the RealDash-forum PD pack
   (`assets/telltales/CREDITS.md`). Covers lighting, wipers, HVAC, engine/
   drivetrain (incl. `engine_map`, `rpm`, `shift_up/down`), brakes (`abs`,
   `parking_brake`, `retarder`), tyres/traction (`tc`, `tyre_pressure`),
   `esp`, transmission, doors/body, driver aids, `page_up/down/left/right`,
   and `media_*`.
2. **Material Icons Round** (`assets/MaterialIconsRound-Regular.otf`, ~400 KB,
   Apache-2.0) — everything else (nav, utility, commands). Rendered by codepoint.

`render_icon` order: ISO tell-tale PNG (drawn **without a frame** — the symbol
is the icon) → Material glyph on a frame → text initials on a frame.
`label_glyph` maps car-control words to the tell-tales.

## Parametric composition (`compose.py`) — a generator

For icons that don't exist as a single PD symbol (engine-start, seat fore/aft/
up/down/recline — ISO 7000-1387/1428/1706/1707, none on Commons) we compose:
a base tell-tale + drawn `arrow` / `arc` / `line` / `tick` layers, all coords
as fractions of the output square. Specs are plain dicts in `COMPOSED`.

`tools/build-composed-icons.py` renders each spec to a **committed** PNG in
`assets/telltales/`, so at runtime they're indistinguishable from the fetched
tell-tales. Edit a spec → re-run the tool → commit. This is the path for any
future "combine two symbols / add an arrow" icon.

## Style layering (current + planned)

    built-in defaults
      └─ settings.icon.game / settings.icon.nav   (two global baselines — no editor UI yet)
           └─ page.style                          (per-page override, done)
                └─ binding.icon_style             (per-key override, done)

`binding.glyph` / `binding.icon_text` pick *what* is drawn; the style layers
pick *how*.

## Navigation — DONE

`settings.nav = {binds: {index: {tap, hold}}}`, tap/hold ∈ home / prev_page /
next_page. Aux L/R default to prev/next page; add a `hold: home` to either.
`home` config keeps only `profile` + `revert_seconds`. Legacy `nav.prev_key` /
`next_key` / `home.key` migrate on load. The `{nav: …}` action puts the same
three functions on any screen key. `+ page` still relocates anything explicitly
bound on the aux keys to the new page.

## Widgets / telemetry

### Partial updates — solved (no hardware RE needed)

`0x000d` (PARTIALLY_UPDATE_BUTTONS) takes the **exact same zip** as SET_BUTTONS
— `manifest.json` + `Images/*.png` — just with fewer cells in the manifest, and
a different opcode. The firmware re-renders only those cells, no full blank.
Proven in `companion-surface-d200` (a shipping Companion surface). Needs a prior
full `0x0001`. So: `layout.build_set_buttons(page, icon_cfg, orientation,
only={indices})` + `device.push_partial()` under `0x000d`.

Companion's cadence: collect dirty cells, debounce ~75ms, flush as one partial.

### The `widget:` binding

A `widget:` field on any key, rendered by us (not the firmware) and refreshed in
place:

    keys:
      13: {widget: clock}                       # replaces the firmware status clock
      3:  {widget: sysload}                      # CPU / RAM / GPU bars
      4:  {widget: shell, cmd: "sensors ...", interval: 5, unit: "°C"}
      5:  {widget: gear, source: sim}            # later

### Provider registry (`widgets.py`)

`Widget(kind, render(size, style, orientation) -> png, interval_s)`. The daemon
holds one instance per provider, ticks them on their interval, and when a
render's bytes change adds the cell to a dirty set → debounced `push_partial`.

- `clock` — HH:MM, 30s tick, only pushes on the minute rollover. Rotation-aware
  (fixes the upside-down firmware clock). Ships first.
- `sysload` — reuses `daemon._sysload()`, 2s tick, bar render.
- `mpris` — now playing (dbus).
- `shell` — run `cmd`, render stdout, `interval` seconds.
- `sim` — per-sim telemetry adapters. Under Proton the rF2/LMU shared memory is
  inside the Wine prefix; likely use the game's UDP/REST telemetry instead.
  AC/ACC use `acpmf_*` shared memory. Start with LMU; research its telemetry
  surface when we get here.

Render: number / bar / mini-gauge, threshold colours (fuel < 10 % → red). The
wide `3_2` slot can host a richer widget (lap + delta + position) — on the D200X
it's just a normal wide button.

### Free wins from the same protocol dig

- **Idle sleep** — DONE, but via `set_brightness(0)` not `0x000f` LOCKSCREEN
  (no re-push semantics to reverse, the drift-watchdog keeps working).
- **Device info** — log the `0x0303` string on connect (firmware / serial). TODO.
- **Drop firmware clock/load** now that the rendered widgets exist. TODO.
