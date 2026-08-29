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

### Phase 3 — web UI
- Single page, vanilla JS, no build step, served by the daemon
- Deck grid (keys + aux + knobs), per-control binding panel
- Icon: file upload **or** generator (text + glyph + bg colour)
- Profile + page management (tabs)
- "Listen" → SSE → capture the next deck press
- Device settings page
- Reachable at `http://<rig-ip>:<port>/` for phone-on-LAN live edits
- `POST /api/preview` — temp-push an icon to one key (icon picker feedback)

### Phase 4 — native wrapper (optional)
- PySide6 `QWebEngineView` + system tray, talking to the same API

## Backlog
- `d200x-button-box` CLI subcommands that hit the API (activate / page / state)
- Icon generator as a reusable module (used by API + GUI)
- Per-key colour / multi-state icons
- Live data on the wide status key (speed, lap, fuel) via a sim-telemetry feed
- Reconnect handling if the deck re-enumerates mid-session
- Package for AUR / a release build
