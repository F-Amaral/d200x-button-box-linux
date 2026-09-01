# Control API

The daemon serves a small HTTP + SSE API (stdlib only, no extra dependency).
It's on by default; disable with `d200x-buttonboxd --no-api`.

```yaml
# settings.yaml
api:
  host: 127.0.0.1     # 0.0.0.0 to reach it from the LAN (e.g. a phone)
  port: 8377
  token: null         # when set, every /api/* call needs it
```

Auth (when `token` is set): send `X-Token: <token>` or `?token=<token>`.
All responses allow CORS (`Access-Control-Allow-Origin: *`).

## Persistent vs transient

- **Persistent** changes (`PUT /api/settings`, `PUT /api/profiles/<name>`) write
  the YAML files. The daemon reloads them within a second and re-renders the
  deck.
- **Transient** actions (`POST /api/activate`, `POST /api/page`) only change the
  running state; they don't touch the files. `activate` sets a manual override —
  `{"profile": "auto"}` clears it.

## Endpoints

| Method | Path | Body | Notes |
|--|--|--|--|
| GET | `/api/state` | | device, active profile + page, profile list |
| GET | `/api/settings` | | current settings as JSON |
| PUT | `/api/settings` | full settings dict | validated by round-trip, then saved |
| GET | `/api/profiles` | | `{profiles: [...], active: "<name>"}` |
| GET | `/api/profiles/<name>` | | the profile (`{keys,knobs}` or `{pages:[...]}`) |
| PUT | `/api/profiles/<name>` | profile dict | saved |
| POST | `/api/profiles/<name>` | | create from the default template if missing |
| DELETE | `/api/profiles/<name>` | | |
| GET | `/api/games` | | `{lmu: {path, can_write}}` — importers + detected install folders |
| GET | `/api/games/<game>/controls` | | `{controls: [names], device_present, bound: {name: button}}` |
| POST | `/api/games/<game>/bind` | `{control, button}` or `{control, clear:true}` | write the game's controller config (409 if the game is running) |
| POST | `/api/profiles/<name>/import` | `{game, path?, overwrite?}` | label the profile from the game's bindings; returns `{applied, skipped, unmatched}` |
| POST | `/api/activate` | `{"profile": "lmu"｜"auto"}` | manual override |
| POST | `/api/page` | `{"page": "next"｜"prev"｜N}` | |
| POST | `/api/icons` | raw image bytes (`Content-Type: image/*`) | saves a 196×196 PNG, returns `{path, url}` |
| GET | `/api/icons/<name>` | | serves an uploaded icon |
| GET | `/api/icon-preview?text=&glyph=&label=&mode=&shape=&border=&fill=&fg=&font=` | | renders a generated icon PNG (`label` → auto glyph or initials) |
| GET | `/api/glyphs` | | `{telltales, material, composed}` — tell-tale names, Material name→codepoint-hex, and which names are composed icons |
| GET | `/api/compose` | | `{name: {spec, builtin, customised}}` for every composed icon |
| GET | `/api/compose/<name>` | | one composed icon's effective spec + flags |
| PUT | `/api/compose/<name>` | `{spec}` | save a user override → render PNG → re-push the deck |
| DELETE | `/api/compose/<name>` | | drop the user override (revert to built-in) |
| POST | `/api/compose/preview` | `{spec, fg?}` | render a spec to a PNG without saving; returns `image/png` |
| GET | `/api/font` | | the bundled Material Icons OTF (for `@font-face`) |
| GET | `/api/events` | | SSE stream (below) |
| GET | `/` … | | the web UI |

## SSE stream (`/api/events`)

`text/event-stream`. Each `data:` line is a JSON object:

```json
{"type": "state",   "device": {…}, "profile": {…}, "profiles": [...]}   // sent once on connect
{"type": "input",   "name": "key3", "index": 3, "kind": "key", "action": "press"}
{"type": "profile", "name": "lmu", "n_pages": 2, "pages": ["drive", "pit"]}
{"type": "page",    "index": 1, "n_pages": 2}
```

The web UI uses `input` events for its "press a key to bind" flow. Comment lines
(`: ping`) arrive every 15 s to keep the connection alive.

## Examples

```bash
curl -s localhost:8377/api/state | jq
curl -s -XPOST localhost:8377/api/activate -d '{"profile":"lmu"}'
curl -s -XPUT localhost:8377/api/profiles/lmu -H 'content-type: application/json' \
     -d @my-lmu-profile.json
curl -N localhost:8377/api/events
```
