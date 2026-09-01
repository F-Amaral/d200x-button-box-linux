# Frontend overhaul — UX plan

The web UI grew feature-first. It works, but every task takes more clicks and
more prior knowledge than it should. This plan starts from *what the user is
trying to do*, lists where the current UI fights them, and defines the target
flow for each. Build order is at the end.

---

## 1. Who uses this, and what for

One persona: a sim racer on Linux, wheel + pedals, usually in a VR headset, the
D200x on the desk as an **auxiliary** button box. They cannot see a keyboard
mid-session. They want a handful of deck buttons wired to things the wheel
doesn't cover — wipers, TC/ABS trim, brake bias, pit request, radio, headlights,
CrewChief shortcuts — with icons they can recognise at a glance while driving,
and the set should follow whichever sim is running.

### Jobs to be done

| # | Job | Frequency |
|---|-----|-----------|
| J1 | First run — plug in, get something usable, understand the 3 control types | once |
| J2 | Bind a deck button to an in-game function | often, early |
| J3 | Make a button recognisable — choose / adjust its icon | often, early |
| J4 | Organise — pages within a profile, and a profile per game + a launcher | occasional |
| J5 | Control per-game switching — auto-detect, manual override, "home" | set once, rely on |
| J6 | Tune the device — brightness, sleep/heartbeat, keyboard grab | rare |
| J7 | (maintainer) author or adjust a shipped icon | rare |

---

## 2. Where the current UI fights the user

### J1 — first run
- Deck cells read "key 5", "enc 18" with no hint what they do or that the aux
  buttons and encoders behave differently.
- No empty state, no "bind your first button" nudge.
- The default profile isn't self-explanatory.

### J2 — bind a button
- The `action` dropdown is fine. `gamepad` + "bind this button in <game>" is
  the right idea but only appears for `gamepad` and only for one detected game.
- "Import from game" is a separate modal, disconnected from the profile it
  edits. It's unclear it's the *fast path* for a whole profile.

### J3 — icons  ← the biggest problem
- **You can't tell what icon a key uses or why.** It's implicit: derived from
  the label's keywords, or the action type, or `binding.glyph` set by... nothing
  in the UI actually sets it.
- The button is called **"style"** but it only edits the *frame* (circle/square,
  fill, border, colours) + up-to-4 letters. Users click it expecting to pick the
  picture.
- Four icon sources — uploaded image, Material Icons glyph, ISO/dashboard
  tell-tale, letter initials — and **no picker for any of them**. A Material
  glyph like `palette` only lands on a key by luck of a label keyword.
- The style cascade (baseline → `settings.icon` → `page.style` → per-key
  `icon_style`) is completely invisible, so "Default icon style" in Settings and
  the page ⚙ have no visible purpose.

### J4 — profiles & pages
- **No create / rename / delete / duplicate for profiles.** The header dropdown
  only *switches* the active one. New profiles appear only as a side effect of
  `POST /api/profiles/<name>` which nothing calls.
- Pages: "+ page" exists; rename is a hidden double-click on the tab; **no
  delete, no reorder**.
- The aux-buttons-become-page-nav behaviour happens silently on the 1→2 page
  step with no explanation.

### J5 — switching
- Auto-detect lives in Settings as game→process-name lists, editable only by
  knowing the shape. No per-profile "this profile is for <game>".
- Home key / home profile / revert-after are three separate Settings rows with
  no plain-language "what this does".

### J6 — device
- The Settings modal mixes device knobs with home/switching. Otherwise OK.
- Brightness/heartbeat/grab are fine; "Grab keyboard" needs one line on *why*.

### Cross-cutting
- **Modal soup** — settings, import, icon-style, icon-editor are 4 `<dialog>`s.
- No undo. Autosave is now on (phase 1) but there's no safety net for a fat-finger.
- Deck previews round-trip to `/api/icon-preview` — a flicker on every edit
  (phase 1 added an `<img>` cache; full fix is client-side rendering).

---

## 3. Target model

1. **The deck is the canvas.** Top of the page, horizontally centred, fixed
   device proportions, always visible. Click a control → it fills the editor.
2. **One editor, docked right, one control at a time.** Action first, then Look,
   then a "More" disclosure for the rare stuff (per-key style override, `hold:`,
   bind-in-game for non-gamepad actions).
3. **Two registers, shown everywhere.** *Sim control* (a car input: gamepad, or a
   still-empty key) → blue, circle motif. *Box control* (nav / profile / command
   / keystroke) → grey, rounded-square motif. On the cell and on the editor.
4. **One slide-over drawer** replaces all modals. Its contents switch: Profiles,
   Settings, Import, Icon library. Never more than one panel deep.
5. **Live + reversible.** Autosave with a visible `saved / editing… / saving…`
   pill; Ctrl-Z undoes the last change to the profile.
6. **Explain in place.** Every non-obvious control gets one line of plain text
   right under it — not in a tooltip, not in docs.

---

## 4. Redesigned flows

### 4.1 Icons — the "Look" section

The editor's **Look** group becomes:

```
label   [ Wipers            ]

icon    ┌────┐   Symbol ▾   ← Auto · Symbol · Letters · Image
        │ 🌧 │   [ wiper            ▾ search ]
        └────┘   showing: ISO tell-tale "wiper"        [customise]
        frame:  ● follows page default   (edit)
```

- **Source selector** (segmented): **Auto** (from label/action — the current
  behaviour, and the default), **Symbol**, **Letters**, **Image**.
- **Symbol** opens a **searchable grid picker**: our ISO / dashboard tell-tales
  and composed icons first (they're the point of this project), then Material
  Icons. Picking one sets `binding.glyph`. The picker shows names and renders
  each tile client-side.
- **Letters** = the current `icon_text` (1–4 chars).
- **Image** = the current upload.
- **caption line** always says what's being shown and where it came from
  ("Auto: Material `palette` from the label", "ISO tell-tale `wiper`",
  "your image").
- **frame** is the old "style" dialog, demoted to a secondary link. It shows
  "follows page default" until you override, and edits `binding.icon_style`.
- **[customise]** appears when the chosen symbol is a composed icon — opens the
  parametric editor (already built).
- If the chosen symbol is a composed tell-tale and needs a lettered variant,
  that's where `compose` gains `text` / `circle` / `rect` layers.

Page ⚙ and `settings.icon.game` / `.nav` are relabelled **"Default look for
this page"** / **"Default look — sim keys / box keys"**, each with a live
preview and one line: *"the frame and colours every auto-generated icon starts
from; a key can override it."*

### 4.2 Profiles

A **Profiles** drawer (opened from the profile name in the header):

- list of profiles, active one marked, "home" one marked;
- row actions: **rename** (inline), **duplicate**, **delete** (blocked for the
  active and home profile with a reason), **set as home**;
- **+ New profile** → name + start-from (blank default / copy of current);
- per row: **"Auto-activate for:"** game chips (writes `settings.auto_detect`);
- needs a new `POST /api/profiles/<name>/rename` (or move) endpoint — today
  rename = delete + recreate and loses the file.

### 4.3 Pages

Page strip under the deck (not in the header):

- click a page name to rename inline; **×** to delete (guard: ≥1 page);
- drag to reorder;
- when going 1→2 pages, a one-time inline note: *"the two round aux buttons now
  flip pages; hold the left one for home."*

### 4.4 Switching (in Settings, its own section)

- **Home**: profile + which key jumps to it + "return to auto-detect after N s
  idle (0 = stay)" — as one sentence with inline fields.
- **Auto-detect**: per profile, the game chips from 4.2, plus a raw
  "process name contains…" escape hatch.

### 4.5 First run

- If the only profile is the untouched default: an overlay on the deck —
  *"This is your deck. 13 LCD keys, 2 round aux buttons, 3 encoders. Click a key
  to bind it, or Import your bindings from a game."*
- Encoder and aux cells carry a small persistent "turn / click" and "page" hint
  until bound.

---

## 5. Design tokens

Dark, intentional. Defined in `webui/style.css` `:root` (phase 1, done).

    --bg #0d0f13 · --surface #14171d · --surface-2 #1b1f27 · --line #2b313c
    --text #e7e9ec · --text-dim #8a929e
    --sim #4a9eff (circle motif) · --box #8b95a3 (rounded-square motif)
    --ok #3ad07a · --danger #ff6b6b · --radius 10px
    type 12 / 13 / 15 / 20 · spacing on an 8px rhythm

## 6. Components

- `Deck` / `Cell` — grid, register tint, selected/hit state, client-rendered icon
- `PageStrip` — rename / delete / reorder / add, aux-nav note
- `Editor` — `ActionField`, `LookField` (source selector + caption + frame link),
  `More` (style override, `hold:`, bind-in-game)
- `KnobEditor` — three `ActionField`s + notes
- `SymbolPicker` — searchable grid; tell-tales + composed first, then Material
- `Drawer` — one slide-over; hosts `ProfilesPanel`, `SettingsPanel`,
  `ImportPanel`, `IconEditor`
- `StatusPill`, `Toast` (undo)

## 7. Tech

**Organised vanilla, no build.** `webui/{index.html, style.css, app.js}` served
statically. Split `app.js` only if it passes ~700 lines and the split is clean.
No `lit` — one screen, ~15 parts, the `el()` helper is enough.

## 8. Compose text / shape layers

Kept separate from `layout.render_icon` (the runtime per-key frame + colour
cascade, which stays). During phase 2, if the `SymbolPicker` + lettered
composed icons need it, `compose` gains `text` / `circle` / `rect` layer types
so letters are just another layer. Otherwise phase 4.

---

## 9. Build order

**Phase 1 — shell (done).** Tokens, deck-as-hero centred layout, docked editor,
sim/box registers, autosave + status pill, `<img>` cache. Dialogs unchanged.

**Phase 2 — the editor & the icon model.**
- `LookField` rewrite ✅ — Auto/Symbol/Letters/Image source selector + live
  preview + caption ("Material icon 'radio'", "dashboard symbol 'wiper'",
  "auto — …") + demoted "Frame & colour" link (hidden when the symbol is a
  frameless tell-tale). `iconSource()` / `iconCaption()` / `usesFrame()`.
- `SymbolPicker` ✅ — searchable `<dialog>` grid, "Dashboard & ISO" (tell-tale
  PNG tiles, lazy) + "Material" (`@font-face` from `/api/font`, rendered by
  codepoint). Sets `binding.glyph`. `/api/glyphs` now also returns `telltales`
  and `material` (name→codepoint hex).
- Page ⚙ ✅ relabelled "Default look — page N" with an explanation line
  (`opts.note` on the icon-style dialog).
- register/baseline alignment ✅ — `layout.is_box_binding()` (nav + command +
  key) now drives the icon baseline both server-side (`resolve_key_icon`) and
  client (`mergedStyle` via `registerOf`), so a command key's icon frame is
  grey like its cell, not blue.
- explicit-look precedence ✅ — a chosen glyph beats chosen letters beats a
  derived (action/label) glyph, on both the device and the web preview. Before,
  Letters had no effect on a key that already had an action-derived glyph.
- glyph + name caption ✅ — a key that shows a picked or action-implied glyph
  (e.g. a profile switch) now renders the label as a small line under the icon,
  so you see both the symbol and the target name. `render_icon(..., caption=)`;
  `/api/icon-preview?caption=`; the web preview sends it too. A glyph that the
  label merely keyword-matched does not repeat the label.
- Look-field polish ✅ — Letters seeds from the label's *initials* (arrow/punct
  stripped), empty when the label has none (was "AB" / "→ L"); Symbol adopts the
  current effective symbol and only opens the picker when there is none;
  `SYMBOL_MEM` remembers the last chosen symbol per key so Auto⇄Symbol toggles
  without re-picking; Auto mode shows "customise <glyph>" when the derived icon
  is composed. Frame & colour dialog: previews the *actual* glyph (not "AB"),
  hides Text/Font for a glyph, greys "Frame fill" when the frame is outline-only,
  relabels Border→"Frame line" / Fill→"Frame fill" / fg→"Icon colour".
- device-push perf ✅ — `device.send_init()` skips the ~8 KB SET_BUTTONS upload
  when the rendered payload is byte-identical to the last one (action/label
  edits that don't change any icon no longer blank the screens); after a real
  push the clock heartbeat fires on the next tick instead of up to 2 s later;
  web autosave debounce 500 → 800 ms.
- **still open:** `More` disclosure (move style-override, `hold:`, bind-in-game
  there; bind-in-game for `key`/`command` too). `settings.icon.game/.nav` has
  no UI at all yet — belongs with the Settings panel in phase 3.
- `compose` `text`/`circle`/`rect` layers — not needed for the picker; deferred
  to phase 4.

**Phase 3 — profiles, pages, drawer.**
- concept text ✅ — the Profiles panel leads with *"A profile is a whole deck
  setup — one per game, plus a launcher… Pages are layers inside a profile; the
  round aux buttons flip between them."*; the page strip repeats the aux note.
- `Drawer` ✅ — one right slide-over (`#drawer` + `#scrim`), Esc / backdrop to
  close. Hosts Profiles / Settings / Import panels, each built as DOM by
  `buildProfiles` / `buildSettings` / `buildImport`. The `<dialog>`s for those
  are gone; the icon editor + symbol picker stay `<dialog>` (nested tools).
- `ProfilesPanel` ✅ — list with active/home tags; per row use / duplicate /
  set-home / delete (guarded), inline rename; ＋ New profile (blank or copy).
  Backend: `config.rename_profile` / `duplicate_profile`,
  `POST /api/profiles/<n>/{rename,duplicate}`, `POST /api/profiles/<n>` takes
  `copy_from`. Rename fixes up `settings.active_profile` / `home.profile`.
- `PageStrip` ✅ — under the deck: click a page to switch, click the active
  name to rename inline, ✕ to delete (≥1 kept), ＋ page, ⚙ default look, aux
  note when multi-page. (drag-reorder not done — low value, skipped.)
- Settings ✅ split into Device / Switching / Connection sections.
- left rail ✅ — on ≥1080px a sticky left column shows the profile list (click
  to activate, click the active name to rename, ＋ New profile inline, Manage…
  opens the full drawer panel); the header profile bar hides. Below 1080px the
  rail collapses and the header "Manage…" button opens the drawer.
- polish ✅ — new-profile is an inline input (no browser `prompt`/`confirm`);
  duplicate name is an inline input; page strip moved *above* the deck;
  deck bottom row is `aux L · aux R · enc · enc · enc` (matches the hardware);
  Frame & colour previews a label-keyword-matched icon (was falling back to "AB").
- brightness ✅ — `settings.yaml` brightness now re-applies to the device on
  reload, not only on connect (`daemon` run loop).
- navigation model ✅ — `settings.nav` is now `{binds: {index: {tap, hold}}}`
  where tap/hold ∈ home / prev_page / next_page (old `nav.prev_key` /
  `nav.next_key` / `home.key` migrate on load; `home` keeps only `profile` +
  `revert_seconds`). The rail's Navigation panel edits it per button with an
  explicit tap / hold dropdown. `_nav_binding` synthesises `{page/profile,
  hold, role:nav}` from it. New **navigate** action (`{nav: home|prev_page|
  next_page}`) puts the same functions on a screen key; `_fire` handles it.
- status strip ✅ — `page.keys[STATUS].status` ∈ clock / load / **off**. The
  SET_SMALL_WINDOW *mode* byte drives the strip: 1 = clock, 0 = system load
  (real CPU/RAM % from `/proc` via `daemon._sysload`), **2 = BACKGROUND** — the
  firmware then shows the status key's own icon (rendered wide, 458×196,
  `_status_icon`) which the manifest carries with `SmallViewMode: 2`. The
  heartbeat sends the matching mode every 2 s (also the keep-alive). Recipe
  found by reading `jcalado/companion-surface-d200` +
  `Tyaaa-aa/Ulanzi-Deck-Linux`; see `docs/hardware.md`. Deck + editor names are
  1-based ("Key 6", "Aux left", "Encoder 1") via `keyName` / `labelFor`.
  `render_icon` now takes a `size` (w, h) — the status "off" icon is rendered
  at the true 458×196 so the Material frame fills the whole wide key, not a
  196px square floating in it. (Confirmed working on the device.)
- more follow-ups ✅ — page/default-look pills moved *below* the deck (deck now
  top-aligns with the side panels); a **Navigation** section in the rail (and the
  Profiles drawer on mobile) sets the home / prev-page / next-page buttons —
  out of Settings; the editor header dropped "sim/box control" for a plain
  role line ("Controller button 5", "Switches profile → lmu", "Home button",
  "Unassigned") + the label as the title; the STATUS key has a **Show the
  clock** toggle (`clock:false` → normal key, `build_manifest` drops
  `SmallViewMode`); Symbol mode no longer force-opens the picker (adopts the
  current auto icon, "Choose…" opens it).
- follow-up fixes ✅ — `actionBlock` re-adds the "bind this button in <game>"
  row that the phase-1 rewrite dropped (shows for a gamepad action when a
  writable game is detected); the Frame & colour link now shows for tell-tale
  symbols too as **Colour** (dialog hides frame/shape/border/fill, leaves Icon
  colour); the default-look dialog reads the *current* page style (was showing
  defaults), its buttons read "Apply" / "Reset to app default", and its note
  says dashboard symbols only take the icon colour.
- **still open:** `settings.icon.game/.nav` "default look" editors (no UI yet);
  auto-detect "this profile is for <game>" chips; the phase-2 `More` disclosure;
  Switching section could move to the rail (user undecided); live key colour
  from telemetry (roadmap backlog).

**Phase 4 — polish (done).**
- no-flash deck icons ✅ — one `<img>` per key id kept across re-renders; a
  changed icon URL only swaps in after the new image has decoded (`deckIcon()`),
  so an edit no longer blanks the cell. (The full client-side render — reproduce
  `layout.render_icon`'s style cascade in CSS/canvas — was **not** done: it
  duplicates the Python and risks the deck preview drifting from the device for
  a flicker the decode-guard already removes. Revisit only if the round-trip
  itself becomes a problem.)
- Ctrl-Z undo + toast ✅ — `UNDO` stack of serialized-profile snapshots, bursts
  of edits within 600 ms coalesce into one step, `#toast` for "Undone" /
  "Nothing to undo". Profile edits only (not settings / nav).
- first-run overlay ✅ — `.introov` card ("This is your deck…" + Import button),
  shown once, gated on `localStorage["d200x_intro"]` (wrapped in try/catch).
- persistent hints ✅ — unbound encoders show "turn · click"; an aux button with
  no nav role shows "round button · set in Navigation".
- keyboard nav ✅ — deck cells are `tabindex=0`, Enter/Space selects, arrow keys
  move the selection along the deck order, Esc clears it.
- focus rings ✅ — `.cell:focus-visible` outline; selected cell + icon swap get
  short transitions.
- drag-to-move ✅ — drag a bound LCD key onto another to move its binding there;
  onto a taken key it swaps. HTML5 DnD, `makeDraggable()`, grid keys only (not
  the wide status key or the screenless aux buttons). Toast "Moved" / "Swapped".
- **daemon:** `D200X_NO_DEVICE=1` skips the hardware entirely (headless UI dev on
  a spare port without fighting the real daemon for the deck).
- not done: empty-state copy is unchanged (already adequate); no richer
  transitions.
