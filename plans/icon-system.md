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

## Widgets / telemetry (backlog — sketch)

A `widget:` field on a key, like the status clock but anywhere:

    keys:
      3: {widget: gear,  source: sim}
      4: {widget: value, source: "shell: sensors -u | ...", refresh: 5, unit: "°C"}

Daemon runs **providers** on a timer and pushes **partial** LCD updates
(`OUT_PARTIALLY_UPDATE_BUTTONS = 0x000d`) at 1–4 Hz:

- `clock` — built-in (already on the status key via the heartbeat)
- `system` — CPU/GPU temp, RAM, from `/sys` + `/proc`
- `mpris` — now playing
- `shell` — run a command, render stdout
- `sim` — per-sim telemetry adapters. The hard one under Proton: rF2/LMU shared
  memory lives inside the Wine prefix; likely need the game's UDP/REST telemetry
  instead. AC/ACC use `acpmf_*` shared memory. iRacing is Windows-only anyway.
  Start with LMU, research its telemetry surface when we get here.

Rendering: number / bar / mini-gauge, threshold colours (fuel < 10 % → red).
The wide status key can host a richer widget (lap + delta + position).
