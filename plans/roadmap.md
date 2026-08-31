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

Phase 3 polish (still TODO):
- icon **generator** (text + glyph + bg colour, canvas → upload)
- delete profile / delete page in the UI
- AC EVO importer (needs a sample of its control-config file — game not installed here)
- `POST /api/preview` — push one icon to the deck live (autosave covers most of this)

### Phase 4 — native wrapper (optional)
- PySide6 `QWebEngineView` + system tray, talking to the same API

## Backlog
- `d200x-button-box` CLI subcommands that hit the API (activate / page / state)
- Icon generator as a reusable module (used by API + GUI)
- Per-key colour / multi-state icons
- Live data on the wide status key (speed, lap, fuel) via a sim-telemetry feed
- Reconnect handling if the deck re-enumerates mid-session
- Package for AUR / a release build
