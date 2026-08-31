# Tell-tale symbols

White-on-transparent PNGs of automotive dashboard symbols, most of them
**ISO 7000** pictograms (the standard road-vehicle controls / indicators /
tell-tales, also in ISO 2575).

## Provenance

Curated and downscaled (to 256×256) from the "Set of ISO 7000 and some other
dashboard icons" pack shared on the RealDash forum:
<https://forum.realdash.net/t/set-of-iso-7000-and-some-other-dashboard-icons/8503>

Per that pack's bundled licensing note, every file is **public domain**:

- ISO 7000 pictograms — the source SVGs on Wikimedia Commons are released under
  **CC0 1.0**; original authorship remains with ISO (Geneva). ISO 7000 symbols
  are simple standardised shapes.
- The `media_*`, `shift_*`, `page_*`, arrow and music icons — released to the
  public domain by the pack's author as simple geometric shapes.
- `ice` — derived from the German StVO (§ 5 Abs. 1 UrhG, public domain).

## Fetched from ISO 7000 SVGs on Wikimedia Commons (public domain)

- `ignition.png` — **ISO 7000-3033A** (starter switch: circle + lightning).
- `headlights_auto.png` — **ISO 7000-2957** (automatic low beam: headlamp + "A").

Rebuild with `tools/fetch-iso-icons.py` (path colours are normalised to white).

## Composed (generated from a spec)

`engine_start` and `seat_fore` / `seat_aft` / `seat_up` / `seat_down` /
`seat_recline` are rendered by `tools/build-composed-icons.py` from parametric
specs in `d200x_button_box/compose.py`: an ISO base symbol (`engine`, `seat`)
plus a drawn arrow / arc / line, matching how ISO 7000 draws
1387 / 1428 / 1706 / 1707 (none of which are on Wikimedia Commons). The arrows
and lines are trivial geometric shapes.

The app tints all of these to the configured icon colour at render time.
