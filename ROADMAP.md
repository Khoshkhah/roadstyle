# Roadmap

The organizing idea (unchanged since the original blueprint): separate **mechanism** — the
styling compiler and map drawer in Python — from **interface** — whatever UI sits on top —
connected by stable contracts. That architecture now exists; this file tracks what's built and
what's next.

## Built (as of 2026-07)

- **One settings file** (`data/defaults.json`) holding every styling default — palettes, config,
  selection, the road width/draw-order model — with a 5-level override ladder
  (`~/.config` → `./roadstyle.json` → `$ROADSTYLE_CONFIG` → `use_settings()` → `settings=` per call).
- **Web backend as the flagship**: per-zoom widths, two-way lanes, oneway arrows, slot-based
  labels, grade separation, 3D ramped + cased bridge decks with a 2D LOD below
  `bridge_decks.flat_below`, base-map switcher incl. tile-less `blank`, compress, offline files.
- **Data contract**: two required columns, everything else additive; `from_duckdb()` for
  DuckDB sources.
- **JavaScript API**: every control scriptable (`rsSetBasemap`, `rsSetClasses`,
  `rsSetColorField`, `rsSetOverlay`, `rsSetView3D`, `rsSelect`/`rsDeselect`) plus the id-set
  query verbs (`rsQuery` → `rsFilter`/`rsColor`/`rsHighlight`/`rsGetProps`/`rsFocus`), on roads
  and overlays alike, with `rs:*` events throughout.
- **UI templates** (`ui/`): copyable HTML scaffolding over the JS API — first: the sidebar
  dashboard — plus **roadstyle studio** (`ui/studio`, Streamlit): the library behind eight
  knobs, generating the equivalent `render_edges` code live.
- **Tooling**: `rs.snapshot()` (headless-browser PNGs), the screenshot-verified test loop,
  the docs gallery (`docs/build_gallery.py`).

## Next

1. **URL hash camera state** — shareable links to an exact view (`hash: true` + a setting).
2. **Find-street box** — search the baked `name` column → `rsSelect` + `rsFocus` (template or
   built-in control).
3. **PyPI release** — prepared (version 0.2.0, tag-triggered `release.yml` via trusted
   publishing, test CI on 3.10–3.13 + a browser smoke job). Remaining: add the trusted
   publisher on pypi.org, push the `v0.2.0` tag; then the sibling projects
   (fetching-sweden-data, traffic_tube) can depend on a pinned release.
4. **Traffic integration demo** — a dashboard fed by the matched Stockholm flow data
   (`color_options` = flow/speed, queries over flow, sensor overlays). The real end-to-end test
   of the whole stack.
5. ~~mkdocs site deploy~~ — done: `.github/workflows/docs.yml` publishes to GitHub Pages on
   every docs change.

Speculative / parked: a deck.gl hybrid for richer 3D, vector-tile output for city-scale data,
generalizing the engine to full base maps (that's the **mapstyle** project's job).
