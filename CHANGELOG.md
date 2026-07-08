# Changelog

All notable changes to **roadstyle** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased] — 0.2.0.dev1

Goal: generalize roadstyle from an OSM-only tool into a reusable, data-driven road-map
styling library that can also be embedded in a website. The existing OSM styling stays
byte-for-byte unchanged; everything new is additive.

### Added
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
