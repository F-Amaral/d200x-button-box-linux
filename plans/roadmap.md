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
- `pytest -q` — parser, payload builder, config round-trips, event routing

## Next — phase 2: control API
- HTTP server in the daemon (stdlib `http.server`, no new dep)
- REST: get/put settings, list/get/put profiles, activate profile, current state
- SSE `/api/events`: stream input events (for "press a key to bind" in the GUI)
- `POST /api/keys/<i>/preview`: temp-push an image to one key
- serve static files (the web UI)
- `api.host` / `api.port` / `api.token` from settings; localhost by default

## Next — phase 3: web UI
- Single page, vanilla JS, no build step, served by the daemon
- Deck grid (keys + aux + knobs), per-control binding panel
- Icon: file upload **or** generator (text + glyph + bg colour)
- Profile + page management (tabs)
- "Listen" → SSE → capture the next deck press
- Device settings page
- Reachable at `http://<rig-ip>:<port>/` for phone-on-LAN live edits

## Next — phase 4: native wrapper (optional)
- PySide6 `QWebEngineView` + system tray, talking to the same API

## Backlog
- Icon generator as a reusable module (used by API + GUI)
- Per-key colour / multi-state icons
- Live data on the wide status key (speed, lap, fuel) via a sim-telemetry feed
- Reconnect handling if the deck re-enumerates mid-session
- Package for AUR / a release build
