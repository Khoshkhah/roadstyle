# Parameters & API

Every public name and every parameter roadstyle takes, grouped by where it appears: types,
defaults, allowed values, and what each one does. Use this as a lookup; for a guided tour see the
[manual](manual.md).

Sections: Public API · render_edges · Stylers · Settings file · StyleConfig · Basemap · RoadStyle ·
Palette JSON · Overlay (use your browser's find, or the page's table-of-contents sidebar).

---

## Public API

Everything in `roadstyle.__all__`, as `import roadstyle as rs; rs.<name>`.

### Rendering

| Name | Returns | Purpose |
|---|---|---|
| `render_edges(gdf, ...)` | `WebMap` / `folium.Map` / `lonboard.Map` | the main entry point — every keyword [below](#render_edges) |
| `render_dashboard(gdf, **kw)` | `WebMap` | **dashboard** page: the map with built-in controls off + the bundled sidebar (query box, colour-by, class filter + legend, results table, read-out) |
| `render_report(gdf, **kw)` | `WebMap` | **report** page: the map + a stats sidebar (KPI cards, colour-by legend, filter, search, selected-road read-out) |
| `render_street_view(gdf, *, panel_width=42, resizable=True, **kw)` | `WebMap` | **map + Google Street View** page: click a road, Street View beside the map looks along it; a draggable divider unless `resizable=False` ([details](web-backend.md#map-and-street-view-side-by-side)) |
| `sidebar_html(name)` | `str` | the bundled sidebar fragment (`"dashboard"` / `"report"` / `"street_view"`) — reshape it and re-inject before `</body>` |
| `snapshot(map_or_html, out_path, *, center, zoom, pitch, bearing, width=1200, height=800, scale=1, settle=2.5, timeout=40)` | path | static PNG via headless Chromium (needs `playwright`) |

`render_dashboard` / `render_report` / `render_street_view` are web-only and take every `render_edges` keyword
(`color_options=` fills the sidebar's *Colour by* picker). The templates ship in the package, so
they need no repo checkout. A `WebMap` has `.html` (the page as a string) and `.save(path)`, and
displays inline in a notebook.

### Input

| Name | Returns | Purpose |
|---|---|---|
| `RoadEdges` | — | the canonical input: EPSG:4326 line geometry + a class column |
| `as_edges(data, *, class_col)` | `RoadEdges` | coerce anything below (what `render_edges` does for you) |
| `normalize_edges(gdf, *, class_col, rename)` | `RoadEdges` | from an in-memory GeoDataFrame |
| `load_edges(path, *, class_col, layer, rename)` | `RoadEdges` | from any geo file (`layer` for multi-layer files, e.g. GPKG) |
| `from_geojson(obj, *, class_col, crs=4326, rename)` | `RoadEdges` | from a GeoJSON mapping or a `to_spec` dict |
| `from_arrow(table, *, class_col, geometry, crs, rename)` | `RoadEdges` | from a pyarrow Table |
| `from_duckdb(con_or_rel, query=None, *, geometry, class_col, crs=4326, rename)` | `RoadEdges` | from a DuckDB connection / relation / query — select the geometry as WKB (`ST_AsWKB(geom) AS geom`) |

### Web / JSON output (the roadstyle.js spec)

| Name | Returns | Purpose |
|---|---|---|
| `to_spec(gdf, ...)` | `dict` | canonical JSON: data + baked-in style + legend + metadata (`color_options` → switchable colouring) |
| `to_geojson(gdf, **kw)` | `dict` | the styled `FeatureCollection` only |
| `to_html(gdf_or_spec, *, full=True, div_id, width, height, **kw)` | `str` | full roadstyle.js page, or an embeddable `<div>+<script>` fragment (`full=False`) |
| `to_iframe(gdf_or_spec, *, width, height, **kw)` | `str` | self-contained `<iframe srcdoc=…>` |
| `save(gdf_or_spec, path, **kw)` | — | write the roadstyle.js page |
| `save_spec` / `load_spec` | — / `dict` | round-trip the spec to a `.json` file |

See [Embedding](embedding.md) for what to do with them.

### Stylers (how colours are chosen)

| Name | Purpose |
|---|---|
| `Styler` | protocol: `resolve_frame(gdf) -> ResolvedFrame` |
| `ClassStyler` | colour by road class via a palette (the OSM default) |
| `CategoricalStyler` | colour by a discrete column + `{value: colour}` map |
| `NumericStyler` | colour by a numeric column via a continuous ramp |
| `ColorTableStyler` | literal per-edge colours, class widths + casing kept (behind `color_table=` and `colors="self"`) |
| `color_by_class` / `color_by` / `color_by_value` | convenience constructors for the first three |
| `build_styler(...)` | pick the right styler from `render_edges`-style kwargs (used internally) |
| `ResolvedFrame` | per-edge resolved style arrays (the renderer's input contract) |

Fields: [Stylers](#stylers-how-colours-are-chosen).

### Palettes, base maps, settings

| Name | Purpose |
|---|---|
| `RoadStyle` | one class's look — [fields](#roadstyle-one-roads-look) |
| `PALETTES`, `HIGHSAT`, `CARTO` | the palette registry (`highsat`, `carto`, `mono`) and two of its tables |
| `SELECTION` | the neon-violet selection profile (`core`, `glow`, `glow_opacity`, `casing`) from the settings' `selection` block |
| `register_palette`, `save_palette`, `load_palette`, `palette_to_dict`, `palette_from_dict` | add palettes; [palette JSON](#palette-json-file) I/O |
| `Basemap`, `BASEMAPS`, `get_basemap`, `register_basemap`, `BaseLayerSwitcher` | base maps — [below](#basemap) |
| `set_api_key(key, provider=None)` / `get_api_key(provider=None)` | set / resolve a base-map API key for this session ([Base maps & API keys](palettes.md#base-maps-api-keys)) |
| `StyleConfig` | global styling knobs — [below](#styleconfig) |
| `use_settings(*sources)` | apply a settings override (path or dict) at runtime; no arguments drops it |
| `Overlay` | an extra layer (zones, POIs, any geometry) for the web backend — [below](#overlay-extra-layers) |

### Style introspection & helpers

| Name | Returns | Purpose |
|---|---|---|
| `resolve(highway, palette, tunnel, bridge)` | `ResolvedStyle` | one edge's resolved style |
| `base_style(highway, palette)` | `RoadStyle` | the palette entry for a class |
| `selection_style(base_width=4.0)` | `dict` | the selection profile scaled to a line width |
| `filter_edges(gdf, include, exclude, ...)` | GeoDataFrame | filter by class |
| `highway_types(gdf)` | `list` | distinct classes present |
| `normalize_highway(value)` | `(base, is_link)` | OSM `_link` normalisation |
| `make_legend(spec, position="bottomleft")` | folium `MacroElement` | a folium legend from a `ResolvedFrame.legend` spec |

---

## `render_edges`

`render_edges(gdf, ...)` builds the map. `gdf` is your road data (a `RoadEdges`, or a
GeoDataFrame with line geometry + a class column; see the data contract on [Home](index.md)).
Every keyword after `gdf` is keyword-only. **On** says which backends read it: *all*, *web*,
*folium*; a keyword a backend doesn't read is ignored.

**Data and styling**

| Parameter | Type | Default | On | Meaning |
|---|---|---|---|---|
| `gdf` | `RoadEdges` / GeoDataFrame | *required* | all | The road edges. A plain GeoDataFrame is normalised for you (→ EPSG:4326, lines). |
| `backend` | `"web"` / `"folium"` / `"lonboard"` | `"web"` | — | Renderer: **`web`** = self-contained MapLibre (vector) map ([web backend](web-backend.md)); `folium` = Leaflet HTML; `lonboard` = GPU/WebGL for very large data. See [engines](engines.md). |
| `palette` | str / dict | `"highsat"` | all | Class palette: `"highsat"`, `"carto"`, `"mono"` or a registered / [custom](palettes.md) one. Ignored by `color_by` / `style`. |
| `highway_col` | str | `"highway"` | all | The column holding the road class **used for styling** (widths, casing, z-order). |
| `include` / `exclude` | str / list / `None` | `None` | all | Keep only / drop these road classes (`exclude` applies after `include`). |
| `match_links` | bool | `True` | all | `primary` also matches `primary_link` in `include` / `exclude`. |
| `color_by` | str / `None` | `None` | all | Colour by a **data column** instead of road class. With `colors` → categorical; with `cmap` (or numeric data) → ramp. |
| `colors` | dict / `"self"` / `None` | `None` | all | For categorical `color_by`: a `{value: hex}` map. `"self"` = the column's value is the **literal** colour (grey fallback for blank / invalid). |
| `cmap` | str / list / `None` | `None` | all | For numeric `color_by`: a ramp name (`"viridis"`, `"YlOrRd"`, matplotlib `"RdYlGn_r"`, …) or a list of hex stops. Default `"viridis"`. |
| `vmin`, `vmax` | number / `None` | `None` | all | Ramp range. Default = the column's min / max. |
| `width_by` | `(min_px, max_px)` / `None` | `None` | all | Numeric styling: scale line width with the value. |
| `color_table` | dict / Series / DataFrame / `None` | `None` | all | Per-edge colour keyed by `color_key`: `{id: colour}`, a Series, or a DataFrame with `color_key` + `color_col`. Edges not in it are **grey**; class widths + casing are kept. |
| `color_key` | str | `"edge_id"` | all | The edges column joined against `color_table`'s keys. |
| `color_col` | str | `"color"` | all | The colour column, when `color_table` is a DataFrame. |
| `style` | `Styler` / `None` | `None` | all | A styler object directly (advanced). Overrides `palette` / `color_by`. |
| `legend` | bool | `True` | web, folium | Draw a data legend for `color_by` / `cmap` / `colors`. Class styling has none; `color_options` maps always get one that follows the *Colour by* dropdown. lonboard draws no legend. |
| `color_options` | mapping / list / `None` | `None` | web | Several **"colour by" options** + a *Colour by* dropdown that recolours in the browser: an ordered `{name: {styler kwargs}}` (or a list of `{"name": ..., **kwargs}`). Blank edges keep the base fill. See [web backend](web-backend.md#dynamic-recolouring-color_options). |
| `color_active` | int / str | `0` | web | Which `color_options` entry is active at load — an index or an option name (unknown name → `0`). |
| `settings` | dict / path / `None` | `None` | all | Per-call settings override (same layout as `roadstyle.json`); applied for this render only, then restored. |

**Base map and camera**

| Parameter | Type | Default | On | Meaning |
|---|---|---|---|---|
| `basemap` | str / `Basemap` / `None` | `None` | all | The primary base map: a key in `BASEMAPS`, a `Basemap`, a `{z}/{x}/{y}` URL template, or an xyzservices provider. Default: the `basemap` setting (`voyager`). |
| `basemaps` | list / `None` | `None` | web, folium | The base maps offered in the switcher. Default on web: `voyager`, `positron`, `dark_matter`, `osm`, `satellite`, `blank`. |
| `basemap_switcher` | bool | `True` | web | The in-map base-layer dropdown (CLI `--no-basemap-switcher`). `False` + an explicit `basemaps=` list keeps them addressable via `rsSetBasemap` (custom UI); `False` alone bakes only the backdrop. |
| `api_key` | str / `None` | `None` | all | API key / token for keyed providers (Mapbox, Stadia, MapTiler, …); falls back to `get_api_key`. |
| `pitch` / `bearing` | number / `None` | `None` | web | Starting camera tilt / rotation in degrees. `None` = the `camera` setting (`0` / `0`). |
| `view_3d` | bool | `False` | web | 3D view: tilted to `camera.pitch_3d` + extruded, ramped, cased bridge decks (knobs in the `bridge_decks` setting). |
| `minzoom` | `None` / `True` / dict | `None` | web | Hide minor classes when zoomed out. `True` = the `minzoom` setting's class → zoom table; a dict overrides parts of it; `None` = every class at every zoom. |

**Page UI and interaction** (web unless marked)

| Parameter | Type | Default | On | Meaning |
|---|---|---|---|---|
| `name` | str | `"roadstyle"` | web, folium | Page title (web) / layer name (folium, default `"roads"`). |
| `arrows` | bool | `True` | web | One-way direction chevrons along each one-way edge (CLI `--no-arrows`). |
| `labels` | bool | `True` | web | Curved street-name labels from the `name` column (CLI `--no-labels`). |
| `filter_control` | bool | `True` | web, folium | The road-class filter panel (CLI `--no-filter`). On folium it shows only when there is no data legend. |
| `filter_col` | str / `None` | `None` | web | The column the filter panel lists, when it should differ from `highway_col` (e.g. widths follow an OSM-highway proxy, the filter lists the source's own `road_class`). |
| `road_popup` | bool / list / `"all"` / `"panel"` | `True` | web | The read-out when a road is **clicked**: `True` = the curated fields (`name`, `edge_id`, `edge_ref`, `highway`, `lanes`, `bridge`, `tunnel`), a list = those columns, `"all"` = every column, `"panel"` = the curated fields in a docked side panel, `False` = none (click-to-select still fires `rs:select`). |
| `popup_mode` | `None` / `"popup"` / `"panel"` | `None` | web | `"panel"` docks the read-out as a full-height side panel (with [search](web-backend.md#built-in-search-panel-mode)) and combines with any `road_popup` field spec; `None` = `"popup"` (floating). |
| `road_tooltip` | bool / list | `False` | web | **Hover** tooltip: `True` = every column, a list = those columns, `False` = off. |
| `tooltip` | list / `None` | `None` | web, folium | Hover columns, the cross-backend name. Web: an alias for `road_tooltip` (used when that is unset); `None` = no tooltip. Folium: `None` = **all** columns. |
| `street_view` | `"window"` / bool | `"window"` | web | Google Street View of the clicked road, facing the edge's direction (no API key). `"window"`: a map button opening a floating window that follows the clicked road; `True`: a plain link in the read-out instead; `False`: none. The URL is also sent as `rs:select`'s `detail.streetView`. See [Street View link](web-backend.md#google-street-view-link). |
| `hover_color` / `select_color` | hex str | `"#b388ff"` / `"#7c4dff"` | web | Highlight colour of the hovered / selected road. |
| `selected` | GeoDataFrame / `None` | `None` | folium | Edges to highlight with a neon-violet overlay. On web use `rsHighlight` / `rsColor` or a `color_options` entry. |
| `legend_position` | str | `"bottomleft"` | folium | Legend corner. |
| `copy_field` | str / `None` | `"edge_id"` | folium | Click an edge → copy this column's value (`None` = off; skipped if the column is absent). |
| `boundary` | geometry / GeoDataFrame / GeoJSON / `None` | `None` | web | A dashed outline on top of the roads (e.g. the clip area). See [boundary overlay](web-backend.md#boundary-overlay). |
| `overlays` | list of `Overlay` / `None` | `None` | web | Extra layers the caller brings — zones, POIs, any geometry. See [`Overlay`](#overlay-extra-layers). |

**Geometry and output** (web unless marked)

| Parameter | Type | Default | On | Meaning |
|---|---|---|---|---|
| `offset_frac` | float | `0.28` | web | Two-way lane offset as a fraction of the road's **pixel** width (constant overlap at every zoom). `0` = no lane split. |
| `width_frac` | float | `0.6` | web | Each two-way lane's width as a fraction of the full width once the directions fan apart (a little over `0.5`, so lanes overlap rather than gap). |
| `offset_zoom` | int | `15` | web | Zoom at which the two directions start fanning into lanes (ramped over ~2 levels). |
| `tunnel_col` / `bridge_col` | str | `"tunnel"` / `"bridge"` | all | Columns marking tunnels (drawn under, dashed + faded) and bridges (on top, heavier casing). lonboard reads them too. |
| `layer_col` | str | `"layer"` | web | OSM `layer` column; a negative value sinks an edge when `tunnel` / `bridge` are absent. |
| `tiles` | bool | `False` | web | Pack the roads as an embedded **PMTiles** vector tileset instead of inline GeoJSON — ~10⁵-edge maps boot in seconds; same single file and JS API. Needs the `tiles` extra; knobs in the `tiles` setting. |
| `compress` | bool | `True` | web | Gzip the inlined sources (3–4× smaller; sources under 256 KB stay plain). `False` = plain JSON, for very old browsers or reading the data out of the file. |

Any other keyword goes to `folium.Map(...)` on the folium backend (e.g. `location`, `zoom_start`).

**Returns:** a `WebMap` (web), a `folium.Map` (folium) or a `lonboard.Map` (lonboard). Save with
`.save("map.html")` (web / folium) or `.to_html("map.html")` (lonboard); all three display inline
in a notebook.

> **Direction arrows.** Geometry direction is the edge's coordinate order, so on a directed routing
> graph each one-way edge points the legal way.

### CLI flags without an obvious keyword

The CLI (see [Home](index.md#command-line)) mirrors the keywords above (`--color-by` → `color_by`,
`--no-arrows` → `arrows=False`, …). The ones that don't map one-to-one:

| Flag | Does |
|---|---|
| `--layer NAME` | the layer to read from a multi-layer file (e.g. a GPKG) — `load_edges(..., layer=)` |
| `-f web` / `folium` | render with that backend (`web` is the default) |
| `-f rsjs` | the roadstyle.js page — `rs.save(...)` |
| `-f spec` | the JSON spec — `rs.save_spec(...)` |
| `-f geojson` | the styled `FeatureCollection` — `rs.to_geojson(...)` |
| `--no-compress` | `compress=False` |

---

## Stylers — how colours are chosen

A **Styler** decides each edge's colour / width. `render_edges` builds one from the arguments
above, but you can construct them directly for full control.

### `ClassStyler` — colour by road class (the OSM default)
| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `column` | str | `"highway"` | Column holding the road class. |
| `palette` | str or dict | `"highsat"` | Palette name, or a `{class: RoadStyle}` dict. |
| `normalize_links` | bool | `True` | Strip the OSM `_link` suffix (`primary_link` → `primary`) and draw links narrower. Turn off for non-OSM data. |
| `fallback` | str | `"unclassified"` | Class used when a value isn't in the palette. |
| `tunnel_col` | str / `None` | `None` | Column marking tunnels (faded + dashed). |
| `bridge_col` | str / `None` | `None` | Column marking bridges (solid black casing, a bit wider). |
| `config` | `StyleConfig` | settings | Opacity / width knobs (see [StyleConfig](#styleconfig)). |

### `CategoricalStyler` — colour by a discrete column
| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `column` | str | — | The column to read the category from (e.g. `"congestion"`). |
| `colors` | dict | `{}` | `{value: hexcolour}`, e.g. `{"low":"#11D68F","heavy":"#F24E42"}`. |
| `fallback_color` | hex str | `"#cccccc"` | Colour for values not in `colors` (and missing data). |
| `missing` | `"base"` / `"self"` | `"base"` | Inside `color_options`: unmapped edges wear the **base option's fill** (`"base"`), or this styler's `fallback_color` (`"self"`, for a loud base palette that would fake a value). |
| `width` | number or str | `2.0` | Constant line width, or the name of a column to read width from. |
| `casing` | hex str / `None` | `None` | Optional constant casing colour (`None` = no casing). |
| `casing_width` | px | `0.0` | Casing width, when `casing` is set. |
| `opacity` | 0–1 | `0.9` | Line opacity. |
| `casing_opacity` | 0–1 | `0.75` | Casing opacity. |
| `dash` | `(on, off)` / `None` | `None` | Optional dash pattern. |

### `NumericStyler` — colour by a numeric column
| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `column` | str | — | The numeric column (e.g. `"aadt"`, `"maxspeed_kmh"`). |
| `cmap` | str / list | `"viridis"` | A branca or matplotlib ramp name (`"viridis"`, `"YlOrRd"`, `"RdYlGn_r"`, …) or a list of hex stops. |
| `vmin`, `vmax` | number / `None` | `None` | Value range mapped across the ramp. Default = data min / max. |
| `width` | number | `2.0` | Constant width (when `width_by` is not set). |
| `width_by` | `(min_px, max_px)` / `None` | `None` | Scale width with the value. |
| `width_column` | str / `None` | `None` | Column driving the width ramp (defaults to `column`). |
| `opacity` | 0–1 | `0.9` | Line opacity. |
| `casing` | hex str / `None` | `None` | Optional constant casing colour. |
| `casing_width` | px | `0.0` | Casing width, when `casing` is set. |
| `casing_opacity` | 0–1 | `0.75` | Casing opacity. |
| `nan_color` | hex str | `"#cccccc"` | Colour for missing / non-numeric values. |
| `missing` | `"base"` / `"self"` | `"base"` | Inside `color_options`: NaN edges wear the base option's fill (`"base"`) or `nan_color` (`"self"`). |

`missing` can also be set per option: `color_options={"Flow": {"color_by": "flow", "missing": "self"}}`.

### `ColorTableStyler` — literal per-edge colours
The styler behind `color_table=` and `colors="self"`: the fill comes from a column of colours,
while widths + casing follow the class palette, so roads still read as roads. No legend.

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `color_column` | str | *required* | Column holding a hex / CSS colour per edge. |
| `highway_col` | str | `"highway"` | Class column the widths + casing come from (absent → a flat 2 px line). |
| `palette` | str or dict | `"highsat"` | Palette for those widths + casing. |
| `fallback_color` | hex str | `"#bbbbbb"` | Colour for blank / missing / invalid values. |

---

## Settings file

EVERY styling default ships in one bundled file — `roadstyle/data/defaults.json` — with four
sections: `palettes`, `config` (the [`StyleConfig`](#styleconfig) fields below), `selection` (the
`SELECTION` profile), and `roads` (the width / draw-order model). A user `roadstyle.json`,
`rs.use_settings(...)`, or `render_edges(..., settings=...)` overrides any part of it — see
[Palettes](palettes.md).

---

## `StyleConfig`

Global styling knobs — the `config` block of the settings file. Defaults reproduce the calibrated
look; change them in a settings override rather than in code. (A `StyleConfig` can also be passed
directly as `ClassStyler(config=...)`.) The dict-valued fields are read by the web backend.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `fill_opacity` | 0–1 | `0.9` | Base opacity of every fill line. |
| `casing_opacity` | 0–1 | `0.75` | Base opacity of every casing line. |
| `casing_extra` | px | `2.0` | Reserved: casing = fill + this (palettes currently set casing widths directly). |
| `link_scale` | 0–1 | `0.7` | How much narrower `_link` roads are than their parent. |
| `tunnel_opacity_scale` | 0–1 | `0.45` | Tunnels fade to this fraction of opacity. |
| `bridge_casing_extra` | px | `1.5` | Bridges get a casing this many px wider. |
| `bridge_casing_color` | hex str | `"#000000"` | Bridge deck casing colour (2D lines and 3D deck strips). |
| `minor_no_casing` | set of str | service, living_street, pedestrian, track, cycleway, footway, path | Classes drawn fill-only (no casing). |
| `minzoom` | dict | motorway 4 … residential 13 … | Class → zoom below which it is hidden; applied only with `render_edges(minzoom=True)`. |
| `basemap` | str | `"voyager"` | The primary base map; per-call `basemap=` overrides. |
| `labels` | dict | `color` `#5b5b5b`, no halo | Street-name label paint: `color`, `halo_color`, `halo_width`. |
| `arrows` | dict | `color` `#5b5b5b`, `opacity` 0.7 | One-way chevron paint. |
| `camera` | dict | `pitch` 0, `bearing` 0, `pitch_3d` 55, `max_pitch` 70 | Starting camera; `pitch_3d` is the tilt of `view_3d` and the 2D/3D button. Per-call `pitch=` / `bearing=` override. |
| `bridge_decks` | dict | `base_m` 5, `thickness_m` 1, `ramp_m` 40, `step_m` 2.5, `match_zoom` 18, `opacity` 0.7, `width_scale` 0.6, `flat_below` 16, `casing_px` 2 | 3D bridge decks (`view_3d`): height, thickness, ramp length, ribbon width matched to the road width at `match_zoom`, flat cased lines below `flat_below`. See [camera & 3D](web-backend.md#camera-3d-view). |
| `overlays` | dict | `color` `#6aa9ff`, `radius` 6, `width` 2, per-kind opacities, `circle_stroke` `#ffffff` | Defaults for every `Overlay`; a per-overlay value wins. |
| `annotations` | dict | `slot_m` 100 | Label / arrow slot length along a road chain (names on even slots, arrows on odd). |
| `tiles` | dict | `minzoom` 6, `maxzoom` 15, `extent` 4096, `buffer_px` 80 | The `tiles=True` tileset's zoom range, MVT extent and clip buffer. |
| `api_key` | str / `None` | `None` | Default base-map API key. |
| `api_keys` | dict | `{}` | Per-provider keys, `{"mapbox": "...", "stadia": "..."}`. See [Base maps & API keys](palettes.md#base-maps-api-keys). |

---

## `Basemap`

A tile provider (the background map under the roads). The built-in keys, keyed providers and API
keys are listed in [Base maps & API keys](palettes.md#base-maps-api-keys); `register_basemap(Basemap(...))`
adds your own, and `get_basemap(key)` resolves a key, a `Basemap`, a `{z}/{x}/{y}` URL template,
or an xyzservices `TileProvider`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `key` | str | — | Short id, e.g. `"dark_matter"`. |
| `label` | str | — | Human name shown in the switcher. |
| `url` | str | — | Tile-URL template (`{z}/{x}/{y}`); `""` = tile-less (plain background, fully offline). |
| `attr` | str | — | Attribution text (credit the tile source). |
| `is_dark` | bool | `False` | Dark canvas? |
| `satellite` | bool | `False` | Apply the satellite saturation / brightness filter. |
| `lonboard` | str / `None` | `None` | Matching basemap name for the lonboard backend. |
| `bg`, `preview`, `subdomains` | str / 3-tuple / str | `"#444"`, greys, `"abc"` | Switcher thumbnail background + road colours; tile subdomains. |

---

## `RoadStyle` — one road's look

A `RoadStyle` describes how a **single road class** (e.g. `motorway`) is drawn. A *palette*
is a dictionary of these, one per class. These are also the fields you see in an exported
palette JSON file.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `fill` | hex colour string | *required* | The road's main (centre) line colour, e.g. `"#FF0000"`. The colour you actually see. |
| `width` | number (px) | *required* | Thickness of the fill line in pixels, e.g. `6`. Bigger = more important road. |
| `casing_width` | number (px) | *required* | Thickness of the **casing** (the outline drawn *under* the fill), e.g. `8`. Usually `width + 2`. Set `0` for no casing. |
| `casing` | hex string or `null` | `"#bcbcbc"` | The casing (outline) colour; `null` = no casing. Light grey by default; legacy files with `casing_dark` still load (it maps onto `casing`). |
| `dash` | `[on, off]` or `null` | `null` | Dash pattern in px, e.g. `[4, 4]` = 4px line, 4px gap (used for footpaths/cycleways). `null` = solid line. |
| `opacity` | number 0–1 | `1.0` | Transparency of the fill. `1` = solid, `0` = invisible. |

> **Casing?** A road is drawn as two stacked lines: a wider **casing** underneath (the border)
> and a narrower **fill** on top (the colour). This is the "geometry sandwich" — it gives every
> road a clean edge. Each class carries ONE `casing` colour (light grey by default in
> `highsat`; per-class hues in `carto`), constant on every base map. Bridge decks keep a solid
> dark casing (`bridge_casing_color`).

> **Units & zoom.** `width` and `casing_width` are **fixed screen pixels** on the `folium` and
> `lonboard` backends — a road keeps the same on-screen thickness at every zoom level. This looks
> right at city scale (roadstyle's main use), but when zoomed far out fixed-pixel roads can blob
> together, and when zoomed far in they don't thicken. The **`web` (MapLibre) backend** instead
> varies width with zoom (the osm-carto width-by-zoom curve), so roads widen smoothly as you zoom
> in — use it when you need zoom-correct widths. See [web backend](web-backend.md).

Example (one entry from the `highsat` palette):
```json
"motorway": {
  "fill": "#00E5FF", "width": 6.0, "casing_width": 8.0,
  "casing": "#bcbcbc",
  "dash": null, "opacity": 1.0
}
```

---

## Palette JSON file

What `save_palette()` writes / `load_palette()` reads. One file fully describes a palette and
can be hand-edited or read by a web frontend.

```json
{
  "name": "highsat",
  "roads": {
    "motorway": { "fill": "#00E5FF", "width": 6.0, "casing_width": 8.0,
                  "casing": "#bcbcbc",
                  "dash": null, "opacity": 1.0 },
    "primary":  { "fill": "#FF9100", "width": 4.5, "casing_width": 6.5,
                  "casing": "#bcbcbc",
                  "dash": null, "opacity": 1.0 }
  }
}
```

| Key | Meaning |
|---|---|
| `name` | Palette name. On load it's registered under this name, so `render_edges(palette=name)` works. |
| `roads` | A map of `class → RoadStyle fields` (see [`RoadStyle`](#roadstyle-one-roads-look)). |

A minimal entry needs only `fill`, `width`, `casing_width`; the rest fall back to defaults.

---

## `Overlay` — extra layers

Extra geometry the caller brings — zone polygons, POI circles, any lines — drawn alongside the
roads on the **`web` backend** via `render_edges(..., overlays=[Overlay(...), ...])`. Each `Overlay`
is *passthrough* data (your geometry, your style); it does **not** go through the road-styling
compiler. See [web backend → Overlay layers](web-backend.md#overlay-layers-overlays).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `data` | GeoDataFrame / GeoSeries / GeoJSON | *required* | The overlay geometry (any CRS → EPSG:4326). Feature `properties` are kept and shown in the click popup. |
| `kind` | `"fill"` / `"line"` / `"circle"` / `None` | `None` | Draw kind. `None` = auto-detect (polygon → `fill`, line → `line`, point → `circle`). |
| `placement` | `"under"` / `"over"` | `"over"` | Draw beneath the roads (e.g. zone fills) or on top (e.g. POIs). |
| `color` | hex str / `None` | `None` → `"#6aa9ff"` | Paint colour (fill / circle / line). |
| `opacity` | 0–1 / `None` | `None` | Layer opacity; `None` = a kind-appropriate default (fill `0.15`, circle `0.85`, line `0.9`). |
| `outline` | hex str / `None` | `None` | Polygon outline colour (`fill` only; default = `color`). |
| `radius` | px / `None` | `None` → `6.0` | Circle radius (`circle` only). |
| `width` | px / `None` | `None` → `2.0` | Line / fill-outline width. |
| `label` | str / `None` | `None` | Name shown in the *Layers* toggle (default `"Layer N"`). |
| `popup` | list / `None` | `None` | Fields shown when a feature is clicked (makes the layer interactive). `None` = show all fields; `[]` = non-interactive (decoration only). In panel mode (`popup_mode="panel"`) the fields dock into the side panel instead of a floating popup. |
| `tooltip` | list / `None` | `None` | Fields shown in a **hover** tooltip that follows the mouse — independent of `popup`, exactly like the road layer's `tooltip` vs `road_popup`. `None`/`[]` = hover only highlights. |
| `visible` | bool | `True` | Initial visibility; the *Layers* toggle starts checked / unchecked to match (`rsSetOverlay` flips it later). |

```python
from shapely.geometry import box
zones = gpd.GeoDataFrame({"taz_id": ["Z0"], "weight": [0.7]},
                         geometry=[box(18.04, 59.31, 18.07, 59.33)], crs=4326)
rs.render_edges(edges, backend="web",
    overlays=[rs.Overlay(zones, placement="under", color="#6aa9ff",
                         opacity=0.14, label="Zones", popup=["taz_id", "weight"])])
```
