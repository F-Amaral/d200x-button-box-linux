# Roadmap

Living doc. Move items between sections as they land.

## Done

### Core (input → gamepad)
- Read D200x interface 0 via `/dev/hidrawN` directly (no hidapi)
- Parse key / aux / encoder reports (indices + actions confirmed on hardware)
- Virtual gamepad via `uinput` (`BTN_TRIGGER_HAPPY*`) — seen by Proton/Wine + KDE
- `EVIOCGRAB` the firmware keyboard (interface 1) so factory macros don't leak
- SET_BUTTONS handshake so interface 0 starts reporting
- `heartbeat_seconds` watchdog (SET_SMALL_WINDOW) so the deck stays in host mode
- `d200x-button-box debug` raw-report dump; `enum` / `status` helpers
- udev rule (`70-` for `uaccess`), systemd user unit
- Verified in Le Mans Ultimate controller binding

### Config
- Split: `settings.yaml` + `profiles/<name>.yaml`
- Bindings: `gamepad` / `key` (ydotool/xdotool) / `command` / `profile` / `page`
- Per-key `label` and `icon` (PNG, auto-resized 196×196)
- Per-game **profiles**, hot-reload on file change
- Process **auto-detect** (`/proc/*/cmdline`) → profile
- **launcher** profile (default) with command + profile-jump examples
- Global **home** button (`settings.home`) with idle auto-revert
- **Multi-page** profiles (`{page: next|prev|N}`), page switch releases held buttons
- Split binaries: `d200x-buttonboxd` (daemon) + `d200x-button-box` (CLI)
- **Mounting orientation** (`device.orientation` 0 / 180) — `orient.py` is the
  sole logical<->physical index map; daemon remaps input at the device boundary
  and turns + replaces icons; the web UI's deck follows (strip moves above,
  status wide-cell to top-left). Everything else stays in logical (as-mounted)
  coords. Encoder direction unchanged; 90/270 out (wide strip can't go portrait).

### Phase 2 — control API
- HTTP + SSE server in the daemon (stdlib `http.server`, no new dep)
- REST: `state`, `settings` (get/put), `profiles` (list/get/put/create/delete),
  `activate`, `page`
- SSE `/api/events`: input events + profile/page changes (press-to-bind)
- static file serving from `webui/` (placeholder page for now)
- `api.host` / `api.port` / `api.token`; localhost by default
- verified on hardware (activate switches the deck live)

- `pytest -q` — parser, payload builder, config round-trips, event routing, API

### Phase 3 — web UI (first cut done)
- Single page, vanilla JS, no build step, served by the daemon at `/`
- Deck grid laid out like the device; per-control binding editor
  (gamepad / key / command / profile / page + label + icon + momentary)
- Knob editor with left / right / click sub-bindings
- Profile dropdown + page tabs, add profile / add page
- Device settings dialog (brightness, heartbeat, grab, home)
- "Listen" → SSE → select the next pressed control
- Icon **file upload** → `POST /api/icons` (normalised to 196×196 PNG)
- verified headless (Chrome-for-Testing + CDP): renders, edits, saves, persists
- single-instance lock (`daemon.lock`, flock)

Phase 3 polish (done):
- redesigned layout — larger deck, centred, editor capped width, grouped fields with hints
- home key badge on the deck grid
- **autosave** toggle (localStorage) — debounced PUT; live deck preview follows edits
- long values ellipsis + hover title
- **Import labels from a game** — `gameimport.py` + `POST /api/profiles/<name>/import`
  + UI dialog. LMU: parses `direct input.json`, id − 32 + 1 = our gamepad button.
  Auto-detects the install folder from Steam libraries.
- `games` in settings
- **stable** control→button map in generated profiles (re-generate never shifts
  bindings); `D200X_CONFIG_DIR` env override

## Next up

### Icon generator + auto-icons — DONE
- `layout.render_icon(style, text)` (Pillow): mode solid|ring, shape circle|round,
  border / fill / fg colours, font sans|condensed|mono|liberation, initials of text.
- **Every LCD key with a label auto-gets a generated icon** (in-memory, at push
  time — no file cache) so the deck is never bare text on black. Status key stays
  clock-only.
- Style is a merge: built-in defaults ← `page.style` ← `binding.icon_style`.
  Per-key `icon_text` overrides the auto initials. Uploaded `icon:` image wins.
- API `GET /api/icon-preview` renders one for the UI. `config.gc_icons()` deletes
  unreferenced uploads after every profile save/delete.
- UI: ⚙ by the page tabs edits page style + name; "style" in the key editor edits
  the per-key override with a live server preview; sync checkbox (fg = border);
  deck cells show the real generated icon.
- Verified on hardware (payload grows to ~20-36 KB / ~20-35 packets, sends fine).

### Bind-to-game — DONE (LMU)
- `gameimport.lmu_controls()` — every bindable control name + which are on our
  device now. `gameimport.lmu_bind(control, button|None)` writes
  `Input[control] = {device: <exact key from file>, id: button + 31}` and a
  one-time `.d200x-bak`.
- Guard rails: refuses if the game process is detected (409); refuses if our
  device isn't in the file yet (bind one control in-game first so the GUID is
  known); only the `Input` section is touched.
- API: `GET /api/games/<game>/controls`, `POST /api/games/<game>/bind`.
- UI: in the key editor, under a `gamepad` binding — "bind this button in LMU"
  dropdown of control names (preselected to the current one) + apply. Clears the
  button's old control then sets the new.
- Verified against a copy of the user's real `direct input.json`.
- Not done for AC EVO / others (need their config format).

### Reconnect handling — DONE
- `device.DeviceGone` raised on fatal read/write errors (ENODEV / EIO / EBADF).
- Daemon starts even with no device — API stays up for config editing.
- On loss: drop the fd, ungrab the keyboard, release held buttons, publish
  `{type: device, connected: false}`. Retries `Device()` every 2 s; on success
  re-grabs the keyboard (node numbers change on re-enumeration) and re-pushes
  the current layout. `snapshot().device.connected` reflects reality; SSE emits
  a `device` event.
- unit-tested (flaky-device fake); happy path hardware-verified. Physical
  unplug/replug not yet tested end to end on hardware.

### Icon system v3 — DONE (see plans/icon-system.md)
- bundled **Material Icons Round** font (`assets/`, ~400 KB, Apache-2.0);
  `glyphs.py` = 53 curated names + aliases
- `layout.render_icon(style, text, glyph)` — a Material glyph or initials
- `glyph:` binding field + **auto-glyph**: nav keys from the action
  (`page:` → chevron, `profile: home` → house, `command:` → terminal); game keys
  from label keywords (headlight / wiper / fuel / radio / …), text initials fallback
- `settings.icon.game` (solid circle, accent) vs `settings.icon.nav`
  (ring, rounded-square, neutral) — the "circle = sim, square = box control" language
- **navigation model**: `settings.nav = {binds: {index: {tap, hold}}}`,
  tap/hold ∈ home / prev_page / next_page (aux L/R default to prev/next);
  legacy `nav.prev_key` / `next_key` / `home.key` migrate on load. `home` keeps
  only `profile` + `revert_seconds`. New `{nav: …}` action puts the same
  functions on a screen key.
- **press-and-hold**: `hold:` on any binding (tap vs hold, `settings.hold_ms`)
- `+ page` relocates anything explicitly bound on the aux keys to the new page
- API: `/api/icon-preview` takes `glyph` / `label` / `caption` / `w` `h`;
  `/api/glyphs` → `{telltales, material, composed}`; `/api/font`

- **automotive tell-tales** — ~108 real dashboard symbols (mostly ISO 7000, all
  public domain — RealDash-forum PD pack) bundled as tintable white PNGs in
  `assets/telltales/` (`telltales.py`), rendered frameless. `ignition` (ISO
  3033A) and `headlights_auto` (ISO 2957) fetched from Commons
  (`tools/fetch-iso-icons.py`).
- **parametric icon composition** (`compose.py` + `tools/build-composed-icons.py`)
  — `engine_start` and the `seat_*` family are specs (base ISO symbol + drawn
  arrow / arc / line), rendered by the tool to committed PNGs in
  `assets/telltales/`. Edit a spec, re-run the tool. The general path for
  combining icons going forward.
- Together they cover the full sim vocabulary: TC, ABS, ESP, engine map, shift
  up/down, brake bias, tyre pressure, fog, hazards, cruise, page nav, media.
  Material Icons for the rest.

### Frontend overhaul — phases 1–3 DONE (see plans/frontend.md)
Deck-as-canvas centred layout, docked editor, sim/box registers, autosave +
status pill; `LookField` (Auto/Symbol/Letters/Image) + `SymbolPicker` +
`@font-face` Material; `Drawer` replacing every modal; Profiles panel
(create/rename/duplicate/delete/set-home + `POST /api/profiles/<n>/{rename,
duplicate}`); page strip (switch/rename/delete/add); left rail on ≥1080px;
Navigation panel (per-button tap/hold); status strip (clock / system load /
custom icon via SET_SMALL_WINDOW mode); device-push perf (byte-identical
SET_BUTTONS skip).

### Frontend overhaul — phase 4 DONE (see plans/frontend.md §9)
No-flash deck icons (decode-guarded `<img>` swap — full client-side render
deliberately skipped), Ctrl-Z undo + toast, first-run overlay, persistent
encoder/aux hints, deck keyboard nav + focus rings, drag a key's binding onto
another key to move / swap it. `D200X_NO_DEVICE=1` for headless UI dev.

### Frontend — phases 2–3 leftovers DONE (see plans/frontend.md §9)
- `settings.icon.game` / `.nav` **default-look editor** — Settings panel "Default
  look" section, two rows (Sim / Box keys) each a live preview + Edit that reuses
  the icon-style dialog; `mergedStyle` / `openFrame` now honour `icon.nav` too.
- per-profile **auto-detect chips** — Profiles panel: "auto-activate when a
  running process matches:" removable chips + free-text add per profile, writes
  `settings.auto_detect`, auto-saves.
- editor **"More" disclosure** — per-key long-press action (`kb.hold`) editor
  (checkbox + nested `actionBlock`); deck cell shows "＋hold". Style override /
  bind-in-game stay inline (contextual, kept where they are).
- bind-in-game for `key` / `command` — **dropped** (a `command` isn't a game
  input; `key` would need the game's *keyboard*-binding format, not the
  controller config — see plans/frontend.md §4 note).

## Next up

### AC Rally support
- installed. Steam **AppId 3917090**, path `…/steamapps/common/Assetto Corsa
  Rally/`, exe `acr/Binaries/Win64/acr.exe`. It is **Unreal Engine 5** (nothing
  like AC EVO's Kunos engine).
- **scaffold DONE** — no `ac_rally` builtin profile: "Import from a game" builds
  it. `gameimport.DETECT_HINTS` (`acr.exe` / `Assetto Corsa Rally`) seeds
  `auto_detect` on import and on fresh bootstrap.
- **config format — good news.** Player rebindings live in a **UE5 GVAS
  SaveGame**: `compatdata/3917090/pfx/…/AppData/Local/acr/Saved/SaveGames/
  EnhancedInputUserSettings.sav`. Standard UE5.4 GVAS (magic `GVAS`, 111 custom
  versions, package `/Game/Data/Input/BC_InputUserSettings…`, then a normal
  property tree). Each mapping is a 4-string run:
  `<HardwareKey> · RawInput · SteeringWheel · <ActionName>`, HardwareKey like
  `GenericUSBController_Button14_346E_0002` (MOZA VID_PID) or `None` if unbound.
  Two profiles (`Default`, `Current1`); `Current1` is active. Full SteeringWheel
  action list: brake, clutch, Handbrake, StartStopEngine, GearUp, GearDown,
  GearR, Gear1..7, SteerWheel, CycleCamera, Look{Left,Right,Back}, CycleLights,
  Toggle{Left,Right}Indicator, Respawn, {Increase,Decrease}{Abs,Tc}, Pause.
- **our device**: virtual pad `D200x Button Box` VID `0x1209` PID `0xD200`
  (`gamepad.py`) → HardwareKey `GenericUSBController_Button<N>_1209_D200`,
  button N **1:1** with our gamepad button N (confirmed against a test binding:
  CycleLights→btn1, CycleWipers→btn3).
- **reader DONE** — `games.ac_rally.read()` scans the .sav's FString runs
  (`<action> <key> "RawInput" "SteeringWheel"`), no GVAS tree parse, no deps.
  `find()` locates it via `compatdata/{3917090,3919070}/…`. In the games
  registry with `can_read` only. Verified end-to-end against the real .sav.
- **per-game code split into a `games/` package** — `games/{lmu,ac_rally,
  ac_evo}.py` each end in `GAME = Game(key, label, detect, find, read?,
  controls?, write?)`; `games/__init__.py` holds the registry + the dispatch
  (`available()`, `read()`, `controls()`, `bind()`, `detect_hints()`);
  `games/steam.py` is the shared library-discovery helper. `gameimport.py` is
  now just `apply_labels` / `prune_to_buttons` (profile glue). Adding a sim =
  one file. `/api/games` sends `label` (frontend `gameLabel` reads it).
- **import flow reworked — builds a profile *for the game***. `POST
  /api/profiles/<name>/import` **creates** `<name>` when missing, then
  `gameimport.prune_to_buttons()` strips it to only the buttons the game
  actually binds (a 2-key `ac_rally` profile, not the 25-button starter map).
  Seeds `settings.games` + `auto_detect`, returns `{created, profile, …}`. Web
  panel: no profile → "creates `ac_rally`"; exists → radio "New `ac_rally-2`" /
  "Update `ac_rally`". Activates the result.
- **AC Rally action names split** — `CycleLights` → "Cycle Lights" (readable +
  the label-glyph matcher can hit); added rally-vocab glyph hints (`cycle
  lights`→headlights_auto, `gear up/down`→shift, `respawn`→refresh, tc/abs, …).
- **profile ↔ game association** — a profile carries an optional `game:` field
  (`Profile.game`, set by import; `/api/profiles` returns a `games` map). The
  page strip has a **🎮 &lt;game&gt;** chip (name only) to link/unlink; the
  **capability** (`read + write` LMU / `import only` AC Rally / `no import yet`
  AC EVO) shows as a tag in the Profiles panel row. The editor's "bind this
  button in &lt;game&gt;" tool keys off the link (falls back to profile name /
  `<game>-N`) and shows only for `can_write` games. `/api/games` gained
  `can_read`; `games.ac_evo` (`find` only, no reader) makes AC EVO a linkable
  "no import yet" game.
- **delete the active profile** — no longer blocked; the daemon falls back to
  the home profile (`active_profile` repointed + forced override cleared). Only
  the home profile itself is protected. `DELETE /api/profiles/<n>` returns
  `{active}`.
- **"New profile" → blank or import** — the ＋ New profile control (rail + the
  Profiles panel) expands to a name field *and* an "⇩ import from a game…"
  button (uses `mousedown` so the input's blur doesn't eat the click).
- **import → straight to the profile** — a clean import closes the drawer, shows
  a toast, and activates the new/updated profile. Only an import with unmatched
  buttons keeps the panel open (you need to see them).
- **daemon:** queued profile/page switches (`/api/activate`, `/api/page`) now
  apply even while the deck is disconnected (were stuck behind the device-poll
  branch) — the web UI stays usable during a reconnect.
- **writer DONE** — `games.ac_rally.write()`. Turned out the mappings are a
  plain `int32`-count-prefixed array inside the profile object (custom UE
  serialization, **not** a tagged `MapProperty`), so **no `Size` fields wrap
  them** — a rebind is a straight FString splice, no tree re-serialization.
  `write()` finds the active profile's run (matched via
  `CurrentProfileIdentifier` → `InputUserSettings.Profiles.*`, falls back to the
  run with the most non-`None` keys), splices the target action's HardwareKey
  (`GenericUSBController_Button<N>_1209_D200` ↔ `None`), and clears any other
  action that was on that button. One-time `.d200x-bak`; the API refuses while
  the game is detected running. `controls()` lists the 30 SteeringWheel actions
  + which of our buttons each is on. Header + `ObjectEnd` tail verified
  byte-identical after a write; mapping count stable. **The game reads the
  rewritten save** (user confirmed).

### Post-writer fixes (bugs the user hit + related asks)
- **bind-in-game "game config not found" after any bind** — `GAME_CONTROLS[game]
  = undefined` (to invalidate) left the key present so `ensureControls` never
  refetched. Now `delete`s it, doesn't cache fetch failures, and re-renders the
  editor after a bind.
- **gamepad `value` no longer a free field defaulting to 1** — it defaults to
  the deck slot's **canonical button** (the stable `default_profile` map: LCD
  key i → i+1, status → 14, encoder subs → 17..25). Shown as text with an
  "override" link for the rare custom case. Stops two keys colliding on button 1.
- **multi-page canonical buttons** — LCD keys on page P now default to
  `P*13 + i + 1` (page 1 → 14..26, …) so page 2's keys don't reuse page 1's
  buttons. Status + encoders stay shared across pages. (Past ~3 pages on a
  40-button pad they can overlap the encoder range — override then.)
- **bind-in-game closes the loop** — a successful bind also labels the deck key
  (`niceControl(action)`) if it has no manual label, so the tell-tale
  auto-detect kicks in. CamelCase action names shown split.
- glyph hints: `respawn` → refresh (was matching `esp` inside "r-**esp**-awn").
- **composed-icon colour layers** — a `compose` layer can carry `color:` to draw
  itself in a fixed colour (tint one arrow of `turn` to mark left/right). The
  key-render tint (`telltales.tint`) now recolours only the greyscale parts of a
  composed PNG and keeps saturated pixels, so the layer colour survives.
- **create a new composed icon** — `＋` in the web icon editor (seeds from the
  current icon, becomes pickable on save); `d200x-button-box icons new <name>
  [--base <telltale>]` on the CLI.
- **`region` compose layer** — recolour / fill part of a symbol, clipped to a
  rect or ellipse. `fill:` floods the enclosed area (hollow + the stroke ring)
  then the strokes are drawn back on top (in `color:` if given, else their
  original colour) — no gap between outline and fill. Achieves "colour the left
  arrow of `turn` blue with a white interior".
- **`icons promote` already reads from `icons.yaml`** — an editor-created icon
  promotes with no manual copy; the misleading "paste into a spec" hint is
  fixed. (No web button — the CLI is enough.)
- **per-label default icon** — `glyphs.action_icon_map()` reads
  `CONFIG_DIR/action_icons.yaml` (`{normalised label -> glyph}`); `label_glyph`
  checks it before the keyword hints. Editable: a "set / change / clear" link in
  the editor's Auto look (picks for every key with that label),
  `GET/PUT /api/action-icons`, `d200x-button-box icons action <label> [glyph]
  [--clear]`.
- AC Rally reader completeness: the `.sav` only holds the 30 SteeringWheel
  actions (all extracted); other menu categories live in the game's `.pak`
  default mapping contexts, not in a rebindable save.

### AC EVO importer + writer — DONE
- AC EVO is Kunos' own engine (not UE). Controls: `compatdata/3058630/pfx/…/
  Saved Games/ACE/input_devices.inputdeviceconfiguration`, a length-delimited
  **protobuf** (no schema). `games/ac_evo.py` has a small varint/LD reader **and
  writer**, no dep. `File{ Device devices=1 }`,
  `Device{ Ident=1, Mapping mappings=2 }`,
  `Mapping{ Control=1 (id in 1/5, dir in 3), button0 uint32=2 }`.
- **Field roles (reverse of the first guess)**: `Control.id` = the game's stable
  control id (per in-game action); `Mapping.button0` = 0-based gamepad button
  (**omitted when 0** = button 1); `Control.dir` 1/2 = the -/+ half of a bipolar
  "cycle" control. The "action drift" seen earlier was just `button0` moving with
  the binding.
- `read()` verified against the real file: all 12 bindings correct, **incl. the
  bipolar Cycle Lights +/-**. `_CONTROL_IDS` = 13 named controls; unknown ids
  still label the button `control N`.
- `write()` splices **only our device's mapping list** — every other device and
  mapping is kept byte-for-byte, a no-op write is a 0-byte diff. Reuses the
  existing `Control` bytes on a rebind. Backup `.d200x-bak`; the API refuses
  while AC EVO runs (it rewrites this file live). **The game accepts a
  d200x-written file** — user confirmed live (moved Flashing Lights btn 1 → 6,
  changed in-game).
- Everything is writable now (see "Game-binding UX" below): `controls()` pulls
  every id bound to any device + the keyboard file, `write()` takes `control
  <id>`, names auto-learn from deck labels or a `tools/acevo-probe.py` pass.

### Game-binding UX (from a use session, 2026-09-02) — DONE
- **Imported game profiles keep the full button map.** Was: `prune_to_buttons`
  stripped every slot the game didn't already bind, and the daemon ignores a
  key with no binding — so a key you wanted to bind in-game did nothing until
  you added a `gamepad` action by hand. Now: no prune; a created game profile =
  the stable map, unlabeled, + imported labels on top. `prune_to_buttons` gone.
  Unlabeled controller keys render a dim button number (`layout.resolve_key_
  icon`), not a black square — web preview too (`previewURL`).
- **Live label refresh while the game runs** — `daemon._sync_game_labels()`, on
  a 3 s tick. If the active profile is linked to a game that's running, re-read
  its config and fill labels for any *unlabeled* deck key it binds; save +
  reload. Only fills blanks, never overwrites. `_GSYNC_POLL`.
- **Phone access** — daemon logs the LAN URL + `ufw allow <port>/tcp` hint when
  `api.host` isn't localhost (`api.serve`). installation.md troubleshooting row.
  Not a code bug — the user's `ufw` was blocking the port.
- **AC EVO — bind without the in-game menu.** Content is a 69 GB encrypted
  `.kspkg`, no readable control names. But `input_keyboard.
  keyboardinputconfiguration` (same protobuf) enumerates ~43 more control ids.
  `ac_evo.controls()` returns every id bound to *any* device in the config
  (`_known_ids` -> `_blob_ids` scans the wheel/pad blocks + the sibling keyboard
  file) -- ~56 unnamed on the dev's setup. `ac_evo.write()` accepts `control
  <id>` and the ` +`/` -` suffix (`_resolve_control`). Controls nobody has bound
  anywhere still don't appear; bind one in-game and the live sync learns it.
- **AC EVO name auto-learn.** `ac_evo.learn(path, {button: label})` remembers
  the labels you put on deck keys, keyed by control id, in
  `CONFIG_DIR/game_names.yaml` (`ac_evo:` section), which overlays `_CONTROL_
  IDS` (`_names()` / `_learned()`, mtime-cached). `daemon._sync_game_labels`
  feeds it every tick while AC EVO runs, and skips `control <id>` placeholders
  when filling blank labels. So: bind a control, label the key, done -- the name
  sticks and shows in the dropdown / `read()`. `Game.learn` is the new optional
  hook. `tools/acevo-probe.py` bulk-binds the unknowns in batches of 38 (pad's
  40-button limit) with a `.acevo_probe.json` sidecar; `--names notes.txt`
  merges what you saw, `--clear` undoes the batch. Send the notes to bake the
  canonical set into `_CONTROL_IDS`. Menu order can't give the ids -- the id
  space has gaps and a bipolar control is one id, not two.
- **Control-icons panel** — `buildActions` / `PANELS.actions`, opened from
  Settings → Default look → "Manage control icons…". Lists every distinct
  control label across all profiles + its resolved icon; pin / change / clear a
  glyph per label via `/api/action-icons`. Skips nav/command keys and the
  `BTN N` placeholders.

## Parked

### Native KDE app — not planned for now
The web UI + systemd user unit cover it. Revisit only if a tray shortcut
(start/stop, quick profile switch) turns out to be missed in daily use. Sketch
if it happens: PySide6 `QWebEngineView` over the same API, `.desktop` +
autostart, no logic duplicated.

## Next up

### Widgets / live cells — 1-4 DONE
`0x000d` partial update = the same zip as SET_BUTTONS with fewer cells, no
blank (proven in `companion-surface-d200`). No hardware RE.

1. ✅ `layout.build_set_buttons(..., only={idx})` + `layout.render_cell` +
   `layout.widget_cells`; `device.push_partial()` under `protocol.CMD_PARTIAL_
   UPDATE` (0x000d).
2. ✅ `widgets.py` — `is_widget` / `interval` / `render`; `clock` (minute),
   `sysload` (CPU/RAM bars, reuses the /proc reader), `shell` (stdout + unit).
3. ✅ `widget:` binding field. Daemon `_tick_widgets` (1s poll) re-renders due
   cells, pushes only the changed ones; state cleared on profile/page switch,
   primed from the full push. `_status_mode()` returns `off` for a widget
   status key so the firmware overlay is disabled. Web UI: status-strip dropdown
   gains "Clock/System load — rendered"; every key gets a Widget section
   (clock/sysload/shell + params); `/api/icon-preview?widget=` previews.
4. ✅ **idle sleep** — `settings.device.idle_sleep_seconds` (default 60, 0=off).
   `daemon._tick_sleep`: on idle → `set_brightness(0)` (the heartbeat keeps
   pinging so the deck stays in host mode); any key wakes it (that press is
   swallowed, not dispatched) → restore brightness + `push_layout`. A running
   auto-detected game counts as activity so it never sleeps mid-race. Chose
   brightness-0 over `0x000f` LOCKSCREEN: no re-push semantics to reverse, and
   the drift-watchdog keeps working.

### Assetto Corsa (the original) — DONE
- `games/ac.py`. Config: `compatdata/244210/pfx/…/Documents/Assetto Corsa/cfg/
  controls.ini` — plain INI, **CRLF** (read/write as bytes to keep it). A button
  action = a section with `BUTTON=`+`JOY=`; axes have `AXLE=` and are skipped.
  `JOY` indexes `[CONTROLLERS]` (`CONn`/`PGUIDn`); our pad's product GUID is
  `D2001209-0000-0000-0000-504944564944`. `BUTTON` is 0-based DInput so
  `BUTTON = gamepad button − 1`. Needs the deck bound once in AC's menu
  (`device_present` = our PGUID is in `[CONTROLLERS]`).
- Covers Content Manager / CSP (`__EXT_*`, `__CM_*`) — ~178 bindable actions on
  the dev's setup. `_NICE` curates the common ones, rest are de-prefixed.
- `write()` rewrites only the target section's `BUTTON`/`JOY` lines + clears a
  conflict on the same button. Backup `.d200x-bak`. Registered in `games.ALL`,
  `BUILTIN_PROFILE_ORDER` (replaced `ac_evo`), launcher template ("-> AC").
- **AC EVO dropped from the README** (table + "Built for" line) — code stays,
  still registered and linkable, just not advertised while it's being validated.

### Auto-detect + sleep fix (2026-09-03) — DONE
- The `lmu` hint was `LeMansUltimate` but the exe/folder is `Le Mans Ultimate`
  (with spaces) — LMU never auto-switched, and since the sleep guard keys off
  the same detection, the deck slept mid-race. Fixed the hint; `from_raw`
  migrates the stale `["LeMansUltimate"]` on load.
- `gamedetect.detect(auto_detect, game_paths)` now also matches the game's
  Steam folder / `compatdata/<appid>` path (from `settings.games`) as a
  fallback, so a bad hint can't blind it. Daemon + the bind-endpoint 409 check
  + `_sync_game_labels` all pass `settings.games`.

### Widgets — still open
- **Drop the firmware default widgets.** Now that `widget: clock` / `widget:
  sysload` render our own (rotation-aware), retire `status: clock` / `status:
  load` (firmware-drawn, can't rotate). Make `widget: clock` the default status.
  Simplifies `daemon._status_mode`, `device.heartbeat` (→ just the keep-alive
  ping), `protocol.build_small_window` (modes 0/1 unused), the status editor.
- `mpris` provider — now playing (dbus).
- `sim` telemetry providers (LMU / AC / ACC) — the hard one; under Proton the
  shared memory is in the Wine prefix, likely need the game's UDP/REST telemetry
  instead. Start with LMU.
- `colour_from:` — a key's fill / colour driven by a telemetry value so the deck
  lights up like a dashboard (rev limiter, TC/ABS engaged, low fuel, pit
  limiter, DRS). Needs the `sim` provider + a re-push throttle.
- richer wide-status widget (lap + delta + position).
- log device info (`0x0303`) on connect (firmware / serial — debugging).

## Backlog
- **compose `text` / `circle` / `rect` layers** — lettered variants of composed
  icons. Deferred from the icon editor (picker didn't need it).
- Visual icon editor phase 3–4 — canvas drag for layer anchors; fold the
  stopgap `<dialog>` into the docked panel. (backend + form done.)
- **AC EVO — run the name-discovery pass** — `tools/acevo-probe.py` batch-binds
  the ~56 unnamed control ids; open AC EVO, note the names, `--names notes.txt`,
  send them to bake into `_CONTROL_IDS`. (Tooling done; the session hasn't run.)
- Per-key press feedback (flash the key on the deck) — cheap now via `0x000d`
- Profile export / import (share a setup as a file)
- "Test" button in the editor — pulse a gamepad button to check it fires
- `d200x-button-box` CLI subcommands that hit the API (activate / page / state)
- Install script + README pass (no AUR needed)
- **Example setups per sim** — ship ready-made profiles for LMU, AC, AC EVO,
  ACC, iRacing (do this last, once everything else is stable)
- CONTRIBUTING + CHANGELOG
- Hardware: physical unplug/replug end-to-end test (reconnect code done, only
  fake-device tested)
