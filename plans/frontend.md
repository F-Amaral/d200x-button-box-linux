# Frontend rethink — design notes

The web UI grew feature-first. Now that the deck has a real visual language
(sim vs box control, readable at a glance, ISO automotive symbols), the editor
should speak the same language. Design first, then rebuild `webui/`.

## What's wrong with the current UI

- **Modal soup** — settings, import, icon-style, page-style are 4 separate
  `<dialog>`s. Editing one key = open/close several.
- **Ad-hoc styling** — greys picked by hand, no type scale, inconsistent
  spacing, buttons styled three ways.
- **The deck isn't the hero** — it's a fixed grid off to the left with an
  oversized empty editor panel next to it.
- **Save-gated** — autosave is opt-in; the deck only follows edits when it's on.
- **No register distinction** — the editor looks the same whether you're
  wiring a car control or a page-nav key.

## Principles (carried from the deck work)

1. **The deck is the canvas.** Big, centred, pixel-accurate to the device.
   Everything else is a panel that serves the selected control.
2. **Two registers, visible.** Editing a *sim control* → blue accent, circle
   motif. Editing a *box control* (nav / profile / command) → neutral accent,
   rounded-square motif. Same split as the device.
3. **Progressive disclosure.** A key needs *action + look*. Advanced (per-key
   style override, `hold:`, bind-to-game) lives under a "More" disclosure.
4. **Live.** Autosave on by default, with a visible "saved / saving" state and
   Ctrl-Z undo of the last change. The deck re-renders as you type.
5. **One settings surface.** Device + nav + icon baselines + API info in a
   single panel with sections, not a modal.
6. **Instant, accurate previews.** Deck cells currently pull server-rendered
   PNGs from `/api/icon-preview`. Options to kill the round-trip / flicker:
   `@font-face` the Material font + `<img>` the tell-tale PNGs directly and tint
   with a CSS mask; or keep server rendering but preload. Decide during phase 1.

## Layout

    ┌───────────────────────────────────────────────┐
    │  header: profile ▾ · page tabs · ⚙ · status   │
    ├──────────────────────┬────────────────────────┤
    │                      │  editor (docked)       │
    │      DECK (hero)      │   selected control     │
    │   5×3 + status + aux  │   action · look        │
    │   + 3 encoders        │   › More               │
    │                      │                        │
    └──────────────────────┴────────────────────────┘
      settings / import open as a full-height right drawer, not a modal

- On narrow screens the editor drops below the deck.
- The deck cells are the real size ratio; status key spans 2; aux + encoders
  are round; the home key carries a small corner mark.

## Design tokens (dark, intentional)

    --bg          #0d0f13   page
    --surface     #14171d   panels
    --surface-2   #1b1f27   inputs, raised
    --line        #2b313c
    --text        #e7e9ec
    --text-dim    #8a929e
    --sim         #4a9eff   sim-control accent
    --box         #7d8794   box-control accent
    --ok          #3ad07a
    --danger      #ff6b6b
    --radius      10px      (round motif: 999px)
    type scale: 12 / 13 / 15 / 20, system-ui, one weight step for emphasis
    spacing: 4 / 8 / 12 / 16 / 24 on an 8px rhythm

## Component inventory

- `Deck` — the grid; renders cells from the active page, emits `select`
- `Cell` — one control; icon (client-rendered) + role tint + selected/held state
- `Editor` — docked panel for the selected control:
  - `ActionField` (gamepad / key / command / profile / page + value)
  - `LookField` (glyph picker | text | upload; live preview)
  - `More` (icon_style override, `hold:`, bind-to-game)
- `KnobEditor` — three `ActionField`s (left / right / click) + notes
- `GlyphPicker` — searchable grid; automotive tell-tales first, then Material
- `SettingsDrawer` — device / nav / icon.game / icon.nav / API
- `ImportDrawer` — game bindings → labels
- `ProfileBar` — profile select, page tabs (rename inline), add/delete

## Tech — no build step

Options, pick one:
- **A. Organised vanilla** — split into `webui/{app.js,deck.js,editor.js,
  style.css}` served statically; a ~30-line reactive-state helper. Zero deps.
- **B. `lit` via local ESM** — bundle `lit` (~6 KB) in `webui/vendor/`; real
  web components, still no build. Better ergonomics for the component tree.

Leaning **B** for the component structure, but A is defensible.

## Phasing

1. tokens + layout shell + client-side icon rendering — the deck looks right,
   nothing else changes
2. docked editor + progressive disclosure + glyph picker
3. settings/import drawers; kill the modals
4. autosave-default + undo; polish (transitions, empty states, keyboard nav)
