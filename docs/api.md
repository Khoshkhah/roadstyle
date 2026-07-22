# API reference

A map of the public API. For every parameter and its meaning, see the
**[Parameter reference](parameters.md)**.

## Rendering

| Function | Returns | Purpose |
|---|---|---|
| `render_edges(gdf, ...)` | `WebMap` / `folium.Map` / `lonboard.Map` | the main entry point — render a styled map (default backend `"web"`) |

Key kwargs: `backend`, `palette`, `highway_col`, `include`/`exclude`, `selected`, `tooltip`,
`basemap`/`basemaps`, `view_3d` / `pitch` / `bearing`, `settings` (per-call override), the
data-driven set `style` / `color_by` / `colors` / `cmap` / `vmin` / `vmax` / `width_by` /
`legend`, and (web backend) `color_options` (switchable colouring), `overlays` (extra layers)
and `compress`.

## Loading & tooling

| Function | Returns | Purpose |
|---|---|---|
| `from_duckosm(db, schema="driving")` | `RoadEdges` | load a duckOSM network with the full data contract (grade tags, oneway, text-safe `edge_id`); `schema` picks the mode — `"driving"` / `"walking"` / `"cycling"` |
| `use_settings(path_or_dict, ...)` | — | apply a settings override at runtime (`use_settings()` drops it) |
| `snapshot(map_or_html, out_png, *, center, zoom, pitch, bearing, ...)` | path | static PNG via headless Chromium (optional `playwright` dependency) |

## Web / JSON output

| Function | Returns | Purpose |
|---|---|---|
| `to_spec(gdf, ...)` | `dict` | canonical JSON: data + baked-in style + legend + metadata (`color_options` → switchable colouring) |
| `to_geojson(gdf, ...)` | `dict` | the styled `FeatureCollection` only |
| `to_html(gdf, full=…)` | `str` | full HTML page or embeddable `<div>+<script>` fragment |
| `to_iframe(gdf, ...)` | `str` | self-contained `<iframe srcdoc=…>` |
| `save(gdf, path, ...)` | — | write a standalone HTML map |
| `save_spec` / `load_spec` | — / `dict` | round-trip the spec to a `.json` file |

## Stylers (how colours are chosen)

| Object | Purpose |
|---|---|
| `Styler` | protocol: `resolve_frame(gdf) -> ResolvedFrame` |
| `ClassStyler` | colour by road class via a palette (the OSM default) |
| `CategoricalStyler` | colour by a discrete column + `{value: colour}` map |
| `NumericStyler` | colour by a numeric column via a continuous ramp |
| `color_by_class` / `color_by` / `color_by_value` | convenience constructors |
| `build_styler(...)` | pick the right styler from kwargs (used internally by `render_edges`) |
| `ResolvedFrame` | per-edge resolved style arrays (the renderer's input contract) |

## Overlays (extra layers)

| Object | Purpose |
|---|---|
| `Overlay` | an extra layer the caller brings (zone polygons, POI circles, any geometry) — drawn under/over the roads on the `web` backend via `render_edges(..., overlays=[...])`. See [parameters §8](parameters.md#8-overlay-extra-layers). |

## Input, palettes, base maps

| Object | Purpose |
|---|---|
| `RoadEdges`, `normalize_edges`, `load_edges`, `as_edges` | canonical input (EPSG:4326, lines) |
| `RoadStyle`, `PALETTES`, `HIGHSAT`, `CARTO` | palette data |
| `register_palette`, `save_palette`, `load_palette`, `palette_to_dict`, `palette_from_dict` | palette extensibility + JSON I/O |
| `Basemap`, `BASEMAPS`, `get_basemap`, `register_basemap`, `BaseLayerSwitcher` | base maps |
| `StyleConfig` | global opacity/width knobs |

## Style introspection & helpers

| Function | Returns | Purpose |
|---|---|---|
| `resolve(highway, palette, tunnel, bridge)` | `ResolvedStyle` | one edge's resolved style |
| `base_style(highway, palette)` | `RoadStyle` | the palette entry for a class |
| `selection_style(base_width)` | `dict` | the neon-violet selection profile |
| `filter_edges(gdf, include, exclude, ...)` | `GeoDataFrame` | filter by class |
| `highway_types(gdf)` | `list` | distinct classes present |
| `normalize_highway(value)` | `(base, is_link)` | OSM `_link` normalisation |
| `make_legend(spec)` | folium `MacroElement` | build a legend from a legend spec |
