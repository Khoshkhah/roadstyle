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
- _(in progress)_ Data-driven styling: color/size roads by any **categorical** or **numeric** column.
- _(in progress)_ Stack-agnostic JSON output (`to_spec`) plus HTML-fragment / iframe emit helpers
  for embedding maps in an existing website.
- _(in progress)_ Input validation with clear error messages; configurable `StyleConfig`;
  registries for custom palettes/themes/basemaps.

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
