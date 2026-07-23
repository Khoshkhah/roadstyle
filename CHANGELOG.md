# Changelog

All notable changes to **roadstyle** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-07-22

First PyPI release.

### Changed
- **`compress` is now on by default** for web maps (3–4× smaller files; sources under 256 KB
  stay inline). `compress=False` / `--no-compress` writes plain JSON. Gzip blobs are stamped
  with `mtime=0`, so the same map now renders byte-identical across runs.
- Version is single-sourced from `pyproject.toml` (`roadstyle.__version__` reads the install
  metadata).

### Added (vector tiles)
- **`tiles=True` (web backend)**: pack the roads — and the street-name/arrow annotation slots —
  as a **PMTiles vector tileset embedded in the single HTML file**, served to MapLibre from
  memory via an in-page `pmtiles://` protocol (vendored pmtiles.js). MapLibre parses only the
  tiles in view: ~10⁵-edge maps boot in a couple of seconds and stay responsive, still offline,
  still one file. Low zooms carry simplified geometry and only the classes the settings
  `minzoom` table shows there. The full JS API, popups and hover/select work unchanged — full
  per-edge attributes travel in a gzipped sidecar table sharing the same index-id space.
  New extra `roadstyle[tiles]` (mapbox-vector-tile + pmtiles), CLI `--tiles`, settings knobs
  under `config.tiles` (zoom range / extent / clip buffer). Class thinning in the tiles
  follows the `minzoom` parameter exactly like the inline version — off by default
  (residential visible at the opening zoom), opt-in with `minzoom=True`. The dashboard builder
  (`ui/dashboard/build.py --tiles`) and both studio pages (a *Vector tiles* toggle) expose it,
  and notebook/studio previews of tiled maps keep the vendored MapLibre v4 (the CDN v3 preview
  predates promise-style `addProtocol`).

### Fixed (grade separation on walking/cycling networks)
- **Solid roads vanished from maps with dashed classes**: `__rs_dash` is baked as null on
  non-dashed edges and MapLibre's `["has"]` counts a present-null as true — the not-dashed
  exclusion filter silently dropped every solid-class road from the fill/casing layers, so
  walking/cycling maps showed the *basemap's* streets instead of roadstyle's (and stacking
  around bridges looked wrong). The filter is now null-safe (`to-boolean`).
- **Stacked structures order by OSM `layer`**: `lvl` now carries the layer value (bridge ≥ +1,
  tunnel ≤ −1), so a layer=3 viaduct draws above a layer=1 footbridge instead of falling back
  to class importance.
- **Dashed-class bridges get a real deck**: the black bridge casing now includes footway /
  cycleway / path bridges, with a solid underlay (the class's light casing colour) beneath the
  dashes — the osm-carto footbridge look. Previously a path bridge drew as bare floating
  dashes, letting whatever passed underneath show through the gaps.
- **Draw-priority review for walking/cycling classes** (aligned with osm-carto's z_order):
  `service` moved BELOW `pedestrian`/`living_street` (was above — a parking alley could cover
  a plaza), `track` slots just above `footway`, `steps` just below (ties used to break
  arbitrarily), and `platform` gets an explicit bottom-of-stack entry (unknown classes default
  to residential priority — railway platforms were drawing at street level). Dashed classes
  (footway/cycleway/path) keep rendering above all solid fills at the same grade — deliberate:
  the subject network of a walking/cycling map stays legible, and a thin dash over a wide fill
  loses nothing.
- Studio: tiled maps preview correctly and show an "embedded vector tiles" badge. Vendored
  MapLibre v4 stalls ANY roads source (GeoJSON or vector) inside sandboxed iframes, so tiled
  previews go through the same CDN v3 slim variant as inline ones — pmtiles.js's Protocol is
  v3-compatible. Verified in a live Streamlit session.

### Added (release engineering)
- CI: lint + tests on Python 3.10–3.13, plus a headless-Chromium smoke test that boots a saved
  map and asserts the data reached MapLibre (`tests/test_web_smoke.py`).
- Tag-triggered PyPI release workflow (trusted publishing).
- The web page template now lives in `static/web_template.html` (was an inline Python string) —
  same output byte-for-byte.
- Docs: kepler.gl comparison + an explicit practical size ceiling for inlined maps.

### Added (2026-07 wave)
- **One settings file** for every styling default (`data/defaults.json`) with the override
  ladder: `~/.config/roadstyle/roadstyle.json` → `./roadstyle.json` → `$ROADSTYLE_CONFIG` →
  `rs.use_settings(...)` → per-call `render_edges(..., settings=...)`. The theme system was
  removed (single light-grey casing; black on bridges; primary base map is a setting).
- **JavaScript API**: `window.rsSetBasemap/rsSetClasses/rsSetColorField/rsSetOverlay/
  rsSetView3D/rsSelect/rsDeselect` — every in-map control scriptable and event-emitting
  (`rs:*` CustomEvents) — plus **id-set queries**: `rsQuery(predicate[, layer])` returns ids;
  `rsFilter/rsColor/rsHighlight/rsGetProps/rsFocus` act on the set, on roads or any overlay.
- **UI templates** (`ui/`): the sidebar dashboard (query box with SQL-style syntax, verb
  buttons, clickable results table → select + fly-to, detail panel, base-map/colour-by selects).
- **3D bridges**: ramped extruded decks with whole-structure hover/select, black side-strip
  casing (`bridge_decks.casing_px`), width trimmed by `bridge_decks.width_scale`, and a 2D LOD —
  flat cased lines below `bridge_decks.flat_below` (default 16) so bridges stay road-width and
  visible at overview zooms.
- **Tile-less base maps** `blank` / `blank_dark` (plain background colour; saved maps make zero
  network requests); `from_duckosm()`; `rs.snapshot()` (headless-browser PNGs); annotation
  slots (alternating names/arrows); `minzoom` class hiding; scale bar + zoom read-out;
  `road_popup="panel"`; overlay styling defaults in settings; compress; the docs gallery.

Goal: generalize roadstyle from an OSM-only tool into a reusable, data-driven road-map
styling library that can also be embedded in a website. The existing OSM styling stays
byte-for-byte unchanged; everything new is additive.

### Added
- **Curated default road popup**: `road_popup=True` (default) now shows a concise field set
  (`DEFAULT_ROAD_POPUP` = name, edge_id, edge_ref, highway, lanes, bridge, tunnel) instead of every
  column — `name` as the bold title (no label), `bridge`/`tunnel` only when the road actually is one,
  and blank / `nan` values dropped. Pass `road_popup=[fields]` for a custom set or `road_popup="all"`
  for every column; `road_popup=False` still disables it.
- **Per-edge colour table**: `render_edges(edges, color_table={edge_id: colour})` paints each edge
  from your own map (dict / `Series` / DataFrame with `color_key`+`color_col`) instead of by road
  class — for clusters, routes, metrics, etc. Edges not in the table get a **gray** fallback; class
  widths + casing are kept so the network still reads as roads. `colors="self"` does the same from
  a colour column already on the data. New `ColorTableStyler`; works on every backend.
- **MapLibre `web` backend is now the default** (`render_edges` `backend="web"`); the CLI's `-f web`
  emits it too and is the default format. The old `-f web` roadstyle.js page moved to **`-f rsjs`**
  (resolving the name clash). Folium-specific features (legends, filter panel) stay on
  `backend="folium"` / `-f folium`.
- **Web-backend UI toggles**: `arrows`, `labels`, `filter_control` (a new collapsible **road-class
  filter panel** — a checkbox per class present, hides that class across every road layer), and
  `basemap_switcher` (the in-map base-layer dropdown). All default `True`; CLI flags `--no-arrows`,
  `--no-labels`, `--no-filter`, `--no-basemap-switcher`.
- **Web-backend boundary overlay**: `render_edges(edges, backend="web", boundary=…)` draws a dashed
  outline on top of the roads (e.g. the area the network was clipped to). Accepts a shapely
  geometry, a `GeoSeries`/`GeoDataFrame` (reprojected to EPSG:4326), or a GeoJSON mapping; `None`
  (default) draws nothing. Rendered as its own `boundary` layer, so it is excluded from the
  road-class filter and from hover/click picking.
- **MapLibre `web` backend** (`render_edges(backend="web")` → a `WebMap` with `.save()`): a
  self-contained, **zoom-correct** vector map matching openstreetmap-carto. Per-zoom road widths
  (osm-carto width-by-zoom curve) instead of fixed pixels; **two-way directional lanes** via a
  pixel-proportional `line-offset` (`offset_frac`/`width_frac`/`offset_zoom`); direction **arrows**
  and curved **street names** (native symbol layers); **hover/select** via `feature-state`; an
  in-map **base-layer switcher**; class-based **draw order**; and **tunnel/bridge grade
  separation** — one baked `lvl` (from optional `tunnel`/`bridge`/`layer` columns) orders tunnels
  underneath (dashed + faded) and bridges on top (heavier, square-capped casing). The saved HTML
  **bundles MapLibre inline and inlines the data**, so it opens offline from disk with no server.
  Distinct from `save`/`-f rsjs` (the roadstyle.js spec page). See `docs/web-backend.md`.
- Command-line interface: a `roadstyle` console script (`roadstyle.cli`) renders any road file
  from the shell — `roadstyle edges.gpkg -o map.html --theme dark`, with `--include/--exclude`
  filtering, data-driven `--color-by/--cmap/--width-by`, and `-f folium|web|spec|geojson` output.
  Every flag mirrors a `render_edges` keyword. No Python required to make a styled map.
- Interactive selection that **returns the result**: clicking a road in `roadstyle.js` fires
  `onSelect(feature, layer)` (and `onDeselect`) with the edge's GeoJSON feature — geometry +
  properties incl. `__rs_class` — plus a `getSelection()` query method, so a custom page UI can
  react (single-select; click again / the map background to deselect). See `docs/embedding.md`.
- Canonical browser renderer: `static/roadstyle.js` (+ `roadstyle.css`) — one drop-in
  `RoadStyleMap` class (headless core: `load`/`setFilter`/`highlightRoad`/`getRoadClasses`, geometry
  sandwich, hover/selection; plus opt-in legend & road-type filter widgets). `to_html` now **inlines
  this same file** instead of a hand-written copy, so the embedded and standalone renderers can't
  drift (enforced by a test). Shipped as package data; documented in `ROADMAP.md`.
- Packaging/quality: MIT `LICENSE`, `py.typed` marker, richer `pyproject.toml` metadata
  (classifiers, keywords, URLs), optional extras (`numeric`, `basemaps`), and `ruff`/`mypy` config.
- Data-driven styling: color/size roads by any **categorical** (`color_by`+`colors`) or
  **numeric** (`color_by`+`cmap`+`width_by`) column, with auto legends; both folium & lonboard.
- Stack-agnostic JSON output: `to_spec` (canonical data + baked-in style + legend), `to_geojson`,
  `to_html(full=…)`, `to_iframe`, `save`, `save_spec`/`load_spec` — embed maps in any website
  (Leaflet / MapLibre / iframe; see `docs/embedding.md`).
- Canonical input layer: `RoadEdges` + `normalize_edges`/`load_edges` (normalize-at-boundary).
- Input validation with clear error messages; configurable `StyleConfig`; registries for custom
  palettes/themes/basemaps; palette JSON I/O (`save_palette`/`load_palette`).
- Docs: parameter reference, embedding guide, frontend-integration guide (baked HTML / JSON API /
  JS port), comparison vs `.explore()`/prettymaps, and a runnable example notebook.

### Verified by adoption
- `sweden-road-data` (`nvdb_acquirer.viz.aadt_map`): renders NVDB vehicle edges coloured by AADT
  traffic volume via `render_edges(color_by="aadt", cmap="YlOrRd", width_by=…)` — confirmed on
  927 real Nacka edges (AADT 1–37,828), both folium & lonboard.

### Fixed
- **Internal `lvl` is hidden from web popups/tooltips.** The web backend injects `lvl` (grade-
  separation elevation, -1/0/+1) for draw ordering; like `twoway` it's now skipped in the default
  popup/tooltip (still present in the feature data for z-ordering). Data columns such as `lanes`
  and `edge_ref` keep showing.
- **Large integer ids no longer round in web popups/tooltips.** Property integers past
  `Number.MAX_SAFE_INTEGER` (2^53) — e.g. a content-hash `edge_id` — were inlined as JSON numbers
  and silently rounded by the browser's `JSON.parse` (last digits changed). They're now emitted as
  JSON **strings**, so they display exactly. Display-only: feature ids are MapLibre-generated
  (`generateId`), so styling / filtering / feature-state / `color_options` are unaffected.
- **`tooltip=` now works on the `web` backend.** The shared `tooltip=` argument (and CLI
  `--tooltip`) was silently swallowed by the web backend, which only read its own `road_tooltip` —
  so the default backend produced no hover tooltip. `tooltip=` is now accepted as an alias that
  fills `road_tooltip` when unset, so the same call works across `web` / `folium` / CLI.
- `roadstyle.js` edge selection now works: clicking a road visibly highlights it (the
  glow is sized to cover the edge, so the colour changes even on wide roads), clicking it again
  or clicking the map background deselects it, and a filtered-out edge drops its selection. The
  highlight overlay is non-interactive so repeat clicks reach the road underneath.

### Changed
- Repositioned as an opinionated OSM road-cartography layer that **reuses** mature libraries —
  `branca` (colormaps + legends), `mapclassify` (numeric classification), `xyzservices` (basemaps) —
  instead of reinventing them.

## [0.1.0]

### Added
- Initial release: OSM-theme road/edge styling for folium & lonboard.
- Two palettes (`highsat`, `carto`); three themes (`light`, `dark`, `satellite`).
- Geometry-sandwich rendering; interactive folium layer (dynamic casing, hover highlight,
  road-type filter panel); thumbnail base-layer switcher; neon-violet selection overlay.
