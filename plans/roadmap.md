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

### Phase 4 — native KDE app
- PySide6 `QWebEngineView` wrapping the web UI + a system-tray icon
  (start/stop daemon, quick profile switch, open UI). `.desktop` file + autostart.
- Lazy path: it's a thin shell over the same API, no logic duplicated.

## Backlog
- Delete profile / delete page in the UI (API already has delete)
- AC EVO importer (needs a sample of its control-config file — not installed here)
- Profile export / import (share a setup as a file)
- "Test" button in the editor — pulse a gamepad button to check it fires
- `d200x-button-box` CLI subcommands that hit the API (activate / page / state)
- Status-key content options (profile name / CPU / — later — live sim telemetry)
- Idle dim after N minutes
- Per-key press feedback (flash the key on the deck)
- `POST /api/preview` — push one icon to the deck live (autosave covers most of it)
- Install script + README pass (no AUR needed)
- **Example setups per sim** — ship ready-made profiles for LMU, AC, AC EVO,
  ACC, iRacing (do this last, once everything else is stable)
- CONTRIBUTING + CHANGELOG
