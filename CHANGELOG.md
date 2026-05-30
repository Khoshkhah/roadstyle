# Changelog

All notable changes to **roadstyle** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased] — 0.2.0.dev0

Goal: generalize roadstyle from an OSM-only tool into a reusable, data-driven road-map
styling library that can also be embedded in a website. The existing OSM styling stays
byte-for-byte unchanged; everything new is additive.

### Added
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
