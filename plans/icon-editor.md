# Visual icon editor — design

Goal: adjust any generated icon by hand in the web UI — nudge the seat arrows,
resize a symbol, or start from a base tell-tale and compose your own — with a
live preview. A GUI over the `compose.py` spec format.

Ships alongside the frontend overhaul (`plans/frontend.md`); this note is the
data model + API + component shape so the backend can land first.

## Data model

A **spec** is the existing `compose.py` dict:

```yaml
base: seat                 # a tell-tale name, or omitted
base_scale: 1.0            # longest side as a fraction of the 256 canvas
base_at: [0.5, 0.5]        # centre, 0..1
layers:
  - {type: arrow, at: [0.54, 0.70], dir: left, len: 0.41, head: 0.14, w: 0.05}
  - {type: arc,   at: [0.5, 0.62], r: 0.185, deg: [175, 357], arrow: end, w: 0.032, head: 0.075}
  - {type: line,  from: [0.06, 0.92], to: [0.78, 0.92], w: 0.042}
  - {type: tick,  at: [0.31, 0.62], dir: up, len: 0.065, w: 0.032}
```

`dir` = up / down / left / right / a number of degrees (0 = right, clockwise).

## Where specs live

| source | file | precedence |
|--|--|--|
| built-in | `compose.COMPOSED` (code) | lowest |
| maintainer | `d200x_button_box/assets/composed.yaml` (committed, from `icons promote`) | middle |
| user | `~/.config/d200x-button-box/icons.yaml` (`{name: spec}`) | highest |

On save the daemon **renders** each user spec to
`~/.config/d200x-button-box/generated/<name>.png` (256px, white). Icon resolution
gains a step:

    user PNG (~/.config/.../generated/) → bundled tell-tale PNG → Material glyph → initials

(`icons/` stays for user-uploaded key images; `generated/` is editor output.)

So a customised `engine_start` overrides the bundled one; a brand-new
`my_tc_plus` becomes a pickable glyph. "Reset" deletes the user spec + PNG.

The daemon never writes into the package on a normal save. `promote_spec()` —
only via `d200x-button-box icons promote <name>` (a maintainer action, needs a
writable source tree) — is the one path that writes `assets/composed.yaml` +
the committed PNG and clears the user override. `compose.COMPOSED` is merged
with `composed.yaml` at import; `render_user_icons(only_missing=True)` at daemon
startup fills gaps in `generated/` without pruning (a hand-edited PNG survives).

## API

| method | path | body / notes |
|--|--|--|
| GET | `/api/compose` | `{name: {spec, customised: bool, builtin: bool}}` for every known composed icon |
| GET | `/api/compose/<name>` | the effective spec + flags |
| PUT | `/api/compose/<name>` | save a user spec → render PNG → reload; body = spec |
| DELETE | `/api/compose/<name>` | drop the user override (revert to built-in, or remove entirely) |
| POST | `/api/compose/preview` | render a spec to a PNG **without saving**; body = `{spec, fg?}`; returns `image/png` |

`GET /api/glyphs` already returns `bases` (all tell-tale names) for the "pick a
base" list and `composed` for the icons the editor knows about — no separate
`/api/telltales` route. Base thumbnails: `POST /api/compose/preview` with
`{spec: {base: <name>, base_scale: 1}}`.

## UI — the editor panel

Reached from a key's icon field: **"customise"** (or right-click a deck cell →
"edit icon"). A panel, not a modal, in the frontend-overhaul layout.

```
┌──────────────┬───────────────────────────────┐
│              │  base   [ seat        ▾ ] [×] │
│   PREVIEW    │  scale  ├────●───────┤  1.00   │
│  (live, on   │  pos X  ├─────●──────┤  0.50   │
│   the key's  │  pos Y  ├─────●──────┤  0.50   │
│   colours)   │  ─── layers ────────────────  │
│              │  ▸ arrow   left  ⣿ ⌄ ✕        │
│              │  ▸ arc     end   ⣿ ⌄ ✕        │
│  [ on deck ] │  [ + arrow ] [ + arc ] [+line]│
│              │  ─────────────────────────    │
│  reset ·save │                               │
└──────────────┴───────────────────────────────┘
```

- **Preview**: the rendered PNG at ~180px, on the key's resolved style colours,
  over both a light and dark chip so contrast is visible. Updates on every
  change, debounced ~120 ms, via `POST /api/compose/preview`.
- **Base**: searchable dropdown of tell-tale names (thumbnails), or "none".
  Scale + position are sliders with a number field; arrow-key nudge = ±0.01.
- **Layer row** expands to its fields:
  - arrow: `at` (X/Y sliders), `dir` (4 buttons + "angle" number), `len`,
    `head`, `w`
  - arc: `at`, `r`, `deg` (start/end), `arrow` (none / start / end), `w`, `head`
  - line: `from` (X/Y), `to` (X/Y), `w`
  - tick: `at`, `dir`, `len`, `w`
  - drag to reorder; ✕ to delete
- **A drag handle on the preview** for the selected layer's `at` point would be
  the nice-to-have (phase 2 of the editor) — click a layer, drag its anchor on
  the canvas.
- **Save** → `PUT`; **Reset** (only if customised) → `DELETE`.
- New icon: "＋ new" asks for a name, starts from `{}` or a copy of the current.

## Phasing

1. **backend** ✅ — user `icons.yaml` + render-to-`~/.config/.../generated/`,
   the resolution step (`telltales._path` prefers `generated/`), the 4 API
   routes, daemon `request_repush()` + startup `render_user_icons()`. Tested:
   `test_compose_editor_roundtrip`.
2. **editor form** ✅ (stopgap `<dialog id="composeDlg">`) — header **Icons**
   button or a key's **customise <glyph>** button. Icon picker, base + scale +
   pos number fields, per-layer `<details>` rows (add / remove / reorder),
   live preview (dark + light chip, debounced 120 ms), Save / Reset. No canvas
   dragging yet. Folds into the overhaul's docked panel in phase 4.
3. **canvas drag** for layer anchors; snap-to-guides; duplicate layer.
4. fold into the frontend overhaul's visual language.
