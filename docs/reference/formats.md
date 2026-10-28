# Inputs and outputs

<p class="lead">The structure and the format of each input of roadstyle (the roads, the level data, the look) and of each output
(the MapLibre style, the road data, the page). The same for the Python engine and the Rust engine.</p>

| | What | Format | Section |
|---|---|---|---|
| Input | the roads | a table of lines: GeoDataFrame, a geo file, GeoJSON, Arrow, DuckDB; the Rust engine reads GeoParquet | [The roads](#the-roads) |
| Input | the level data | 8 columns in the roads, or a duckOSM file | [The level data](#the-level-data) |
| Input | the look | a palette and a profile (YAML), settings (JSON or YAML), the keywords of `render_edges` | [The look](#the-look) |
| Internal | the merged look | JSON, between the look and the engine | [The merged look](#the-merged-look) |
| Output | the MapLibre style, the road data, the page: other files for each way (default, A, B, C) | JSON, GeoJSON or vector tiles, HTML | [The output of each way](#the-output-of-each-way) |

How the parts work together: [How a map is drawn](../rust/drawing.md).

## The roads

One row for each **directed edge**: its geometry runs the way traffic flows, and a two-way road is two edges with reversed
geometry. `render_edges` takes a GeoDataFrame, a file path, a GeoJSON mapping, a pyarrow Table or osmnx edges
([Loading data](../get-started.md#loading-data)). A column of osmnx lists (`name=['Götgatan', 'Ringvägen']`) becomes its first
value.

| Column | Type | Needed | Other name with | What it does |
|---|---|---|---|---|
| `geometry` | LineString or MultiLineString, any CRS (reprojected to EPSG:4326) | yes | | the line of the edge |
| `highway` | text: an OSM class (`primary`, `residential`, ...; a `_link` class is drawn at `roads.links.width` of its main class) | yes | `highway_col` | the width, the casing, the color and the order where roads meet (the profile's `roads.classes`) |
| `name` | text | no | | the street names and the popup title |
| `oneway` | true, or a value that is not empty, `no`, `false` or `0` | no | | the one-way arrows |
| `bridge`, `tunnel` | the same truth values | no | `bridge_col`, `tunnel_col` | the bridge and tunnel looks, and the level when there is no `layer` |
| `layer` | a number (an integer, or text that is a number) | no | `layer_col` | the OSM layer: the level of a crossing |
| `edge_id` | an integer or text; kept exact past 2⁵³ | no | `edge_id_col` | the id in the popup, the search and the JavaScript API |
| `access` | `private`, `bus`, `pedestrian`, `delivery`, or empty | no | `access_col` | the access colors and the access filter |
| a width in metres | a number | no | `width_m_col` | the road drawn at its real width, from `width_m_zoom` |
| a directed flag | true or empty: a direction of its own; false: undirected | no | `directed_col` | a two-way pair of undirected edges is one line |
| a driving flag | true or empty: cars can drive it; false: they cannot | no | `driving_col` | the one-way arrow only on an edge for cars |
| a filter class | text | no | `filter_col` | the classes in the Roads box, when they differ from `highway` |
| the level data | see the next section | no | | the drawing order |
| any other column | any | no | | in the popup, and in `rs.query` |

**The Rust engine** reads the roads as GeoParquet: the geometry as WKB in a column `geometry`, in EPSG:4326, and the columns above
by the names that the keywords give. From Python, `render_edges` writes this file for you. In the browser, write
it with GeoPandas (`rs.as_edges(edges).gdf.to_parquet(path, index=False)`), or with `writeRoads` from a duckOSM file.

**The columns of `writeRoads`** (`rust/roadstyle-wasm/js/roads_sql.js`), one row for each edge of a duckOSM file:
`edge_id`, `osm_id` (text), `highway`, `name`, `bridge`, `tunnel`, `layer`, `oneway`, `walk_type`, `junction`, `edge_ref`,
`lanes`, `driving`, `walking`, `cycling` (the modes that use the edge), `access`, `geometry` (WKB), the 8 level columns, and
`is_directed` and `has_arrows` (the directed and driving flags).

## The level data

Eight columns for each edge give the drawing order. They are inputs of the rendering, as the other columns are
([Which road is on top](../guides/levels.md)).

| Column | Type | What it does |
|---|---|---|
| `casing_level` | integer | the position of the casing of the middle of the edge |
| `fill_level` | integer | the position of the fill |
| `casing_start`, `casing_end` | integer | the positions of the casing heads at the start and at the end of the edge |
| `head_start_m`, `head_end_m` | number, metres; empty: the look's `head_m` (5 m) | the length of each head |
| `cap_start`, `cap_end` | true (a square end), false or `"round"` (a round end); empty: the value of `cap_col` | the end caps |

Where they come from:

- **The solver:** `rs.compute_levels(edges)` adds the 8 columns. Without level columns, `render_edges` runs it by itself.
- **Your own columns:** name them with `casing_level_col`, `fill_level_col`, `casing_start_col`, `casing_end_col`,
  `head_start_m_col`, `head_end_m_col`, `cap_start_col`, `cap_end_col` (or `cap_col` for both ends).
- **A duckOSM file:** `render_edges(..., levels_db="area.duckdb")` reads them from two tables:

| Table | Columns |
|---|---|
| `visualization.edge_levels` | `edge_id` (BIGINT), `casing_start`, `casing_level`, `casing_end`, `fill_level` (BIGINT), `head_start_m`, `head_end_m` (DOUBLE), `cap_start`, `cap_end` (VARCHAR) |
| `visualization.edge_levels_meta` | `source` (how the levels were made: `area`, `tags` or `solve`), `area`, `n_edges`, `edge_hash` (the SHA-256 of the sorted edge ids, so the levels fit only these edges), `roadstyle_version`, `created` |

## The look

The look is the set of choices of a map. It has four parts, merged in this order: the profile, the palette, the settings, and the
keywords of `render_edges`. A file of your own states only what it changes
([Settings & palettes](settings.md)).

### The profile

Every value that is not a color: widths by zoom, zoom ranges, sizes, dashes, caps, spacing and the tunnel look. Pick it with
`profile="<name>"`; your own file is `./profiles/<name>.yaml`. Widths are pixels at the zoom given, unless the key ends in `_m`
(metres).

<!-- gen:profile -->
Bundled: `default`, `highsat`. The table shows `default`; the others state only what they change.

| Key | Value in `data/profiles/default.yaml` | Comment in the file |
|---|---|---|
| `roads` | `13 entries: classes, fallback, width, width_zoom_rate, ...` |  |
| `roads.classes` | `27 entries: motorway, trunk, primary, secondary, ...` | per class: group (its row in width), order (higher = drawn on top where roads meet), minzoom (hidden below, with render_edges(minzoom=True)), no_casing (fill only), single_line (a two-way pair is one line), minor (arrows and names later, smaller arrows), width / casing_width / dash (folium and lonboard; dash also on the web map). |
| `roads.fallback` | `{"group": "residential", "order": 4, "link_order": -0.5, "width": 2.0…` | a class with no entry |
| `roads.width` | `9 entries: major, primary, secondary, tertiary, ...` | px by zoom, per group (the web map) |
| `roads.width_zoom_rate` | `9 entries: major, primary, secondary, tertiary, ...` | growth per zoom past the last stop |
| `roads.casing_ratio` | `9 entries: major, primary, secondary, tertiary, ...` | casing width = fill width x ratio |
| `roads.zoom_stops` | `[12, 13, 14, 15, 16, 17, 18, 19, 20]` |  |
| `roads.links` | `{"classes": ["motorway_link", "trunk_link", "primary_link", "secondar…` | width: of the main class's width |
| `roads.cap` | `"round"` |  |
| `roads.join` | `"round"` |  |
| `roads.split` | `{"offset_frac": 0.28, "width_frac": 0.6, "offset_zoom": 15, "ramp_zoo…` | two-way roads: each direction offset_frac of the road width aside, width_frac wide, from offset_zoom over ramp_zooms |
| `roads.width_m_zoom` | `16` | roads in metres (width_m_col): the zoom where a metre width equals the class width |
| `roads.twin_end_caps` | `true` | one road-wide round end under a two-way road's two lanes |
| `roads.twin_casing` | `"one"` | a two-way road as two edges: one casing around both, or each its own |
| `casing` | `{"extra": 2.0, "m": 0.15, "min_px": 0.0, "drop_below_px": 1.0}` | m, min_px: roads in metres; drop_below_px: no casing piece where the casing line is narrower than this (0 = always a casing) |
| `labels` | `10 entries: halo_width, font, glyphs, minzoom, ...` |  |
| `labels.halo_width` | `0` |  |
| `labels.font` | `["Noto Sans Regular"]` |  |
| `labels.glyphs` | `"https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf"` |  |
| `labels.minzoom` | `14` |  |
| `labels.minor_minzoom` | `16` |  |
| `labels.fraction` | `0.9` | a name fits inside its road: at most this part of the road width |
| `labels.min_px` | `8.0` | no name smaller than this |
| `labels.base_size` | `[[14, 10], [18, 14]]` | px by zoom: the size a name starts from (labels.size: one table for every class) |
| `labels.max_angle` | `40` |  |
| `labels.padding` | `2` |  |
| `arrows` | `8 entries: minzoom, minor_minzoom, main_below, size, ...` |  |
| `arrows.minzoom` | `15` |  |
| `arrows.minor_minzoom` | `16` |  |
| `arrows.main_below` | `16.5` | the page: below this zoom only the main classes (motorway ... tertiary) get arrows (2026-10-19: was 17) |
| `arrows.size` | `{"base": 1.8, "stops": [[15, 0.5], [18, 0.9], [22, 3.0]], "minor": 0.…` | icon size by zoom; minor classes x minor |
| `arrows.spacing` | `[[15, 200], [18, 320], [22, 900]]` | px between repeated arrows (tiles=True) |
| `arrows.icon` | `{"path": "M 0,2 7,2 7,0 12,2.5 7,5 7,3 0,3 z", "view_box": [12, 5], "…` | drawn 4x large: the size ramp scales it up to ~10x |
| `arrows.main` | `["motorway", "trunk", "primary", "secondary", "tertiary"]` | the main classes (and their links), with arrows below main_below |
| `arrows.place` | `{"min_len_px": 100, "min_gap_px": 150, "name_gap_px": 14, "edge_px": …` | the page: no arrow on a road shorter than min_len_px on screen; arrows min_gap_px apart; name_gap_px beside a name; edge_px from the window edge; a name's width = its letters x char_width x its size |
| `bridges` | `8 entries: cap, wing_scale, ramp, casing_extra, ...` |  |
| `bridges.cap` | `"butt"` | square deck ends |
| `bridges.wing_scale` | `1.25` | the deck casing: the road casing width x this |
| `bridges.ramp` | `[14, 17]` | simple mode: the wings and the shadow grow from the first zoom to the second |
| `bridges.casing_extra` | `1.5` | px wider than a road casing (the deck wings) |
| `bridges.casing_m` | `0.25` | metre widths: at least this wide each side |
| `bridges.casing_px` | `1.0` | and never thinner than this each side |
| `bridges.shadow` | `{"show": true, "blur": 4.0, "offset": [2, 2], "trim_m": 3.0, "width_s…` |  |
| `bridges.decks` | `8 entries: base_m, thickness_m, ramp_m, step_m, ...` | view_3d: the extruded decks |
| `tunnels` | `9 entries: opacity_scale, cap, folium_dash, casing_dash, ...` |  |
| `tunnels.opacity_scale` | `0.45` | folium / lonboard: a tunnel fades to this |
| `tunnels.cap` | `"butt"` | clean dash ends |
| `tunnels.folium_dash` | `[4, 4]` | folium / lonboard: a tunnel of a solid class gets this dash |
| `tunnels.casing_dash` | `[1, 1]` | dash and gap, in line widths |
| `tunnels.fill_dash` | `[]` |  |
| `tunnels.strength` | `60` | 0 = normal colors, 100 = the full tunnel colors |
| `tunnels.dash_extra_px` | `3` | the dash layer and the casing under it: px wider than a casing |
| `tunnels.steps` | `[0, 25, 50, 55, 60, 65, 70, 75, 100]` | the Tunnels box: the strength slider's steps |
| `tunnels.ratios` | `[[1, 1], [2, 2], [3, 3], [4, 4], [2, 1], [3, 2], [4, 3], [1, 2]]` | the Tunnels box: the dash ratios to choose from |
| `selection` | `{"folium": {"base_width": 4.0, "glow_scale": 3.0, "casing_scale": 1.8…` |  |
| `data` | `{"width": 2.0, "casing_width": 0.0}` |  |
| `overlays` | `8 entries: radius, width, circle_stroke_width, text_size, ...` |  |
| `overlays.radius` | `6.0` |  |
| `overlays.width` | `2.0` |  |
| `overlays.circle_stroke_width` | `1` |  |
| `overlays.text_size` | `12` |  |
| `overlays.text_max_angle` | `40` |  |
| `overlays.text_padding` | `2` |  |
| `overlays.text_halo_width` | `1.5` |  |
| `overlays.item_overlap_px` | `1` |  |
| `boundary` | `{"width": 2.5, "dash": [3, 2]}` |  |
<!-- /gen:profile -->

### The palette

Every color, and nothing else. Pick it with `palette="<name>"`; your own file is `./palettes/<name>.yaml`.

<!-- gen:palette -->
Bundled: `amber`, `carto`, `highsat`, `mono`. The table shows `amber`; the others state only what they change.

| Key | Value in `data/palettes/amber.yaml` | Comment in the file |
|---|---|---|
| `classes` | `13 entries: motorway, trunk, primary, secondary, ...` | per road class: fill, casing (null = no casing), opacity |
| `classes.motorway` | `{"fill": "#f28c28", "casing": "#dc2a48", "opacity": 1.0}` |  |
| `classes.trunk` | `{"fill": "#f5a623", "casing": "#c84e2f", "opacity": 1.0}` |  |
| `classes.primary` | `{"fill": "#f4c542", "casing": "#a06b00", "opacity": 1.0}` |  |
| `classes.secondary` | `{"fill": "#f7df72", "casing": "#707d00", "opacity": 1.0}` |  |
| `classes.tertiary` | `{"fill": "#b8d986", "casing": "#bcbcbc", "opacity": 1.0}` |  |
| `classes.unclassified` | `{"fill": "#ffffff", "casing": "#bcbcbc", "opacity": 1.0}` |  |
| `classes.residential` | `{"fill": "#d7dee8", "casing": "#bcbcbc", "opacity": 1.0}` |  |
| `classes.living_street` | `{"fill": "#cbd5e1", "casing": "#cccccc", "opacity": 1.0}` |  |
| `classes.service` | `{"fill": "#94a3b8", "casing": "#d4d4d4", "opacity": 1.0}` |  |
| `classes.track` | `{"fill": "#a3a3a3", "casing": "#9e7b54", "opacity": 1.0}` |  |
| `classes.cycleway` | `{"fill": "#5c7cb6", "casing": "#5c7cb6", "opacity": 1.0}` |  |
| `classes.footway` | `{"fill": "#C59D9D", "casing": "#C59D9D", "opacity": 1.0}` |  |
| `classes.path` | `{"fill": "#C59D9D", "casing": "#C59D9D", "opacity": 1.0}` |  |
| `roads` | `{"fallback": {"fill": "#888888", "casing": "#000000", "palette_casing…` |  |
| `casing` | `{"opacity": 0.75}` |  |
| `labels` | `{"color": "#5b5b5b", "halo_color": null}` |  |
| `arrows` | `{"color": "#5b5b5b", "opacity": 0.7}` |  |
| `bridges` | `{"casing_color": "#64748b", "shadow": {"color": "rgba(0,0,0,0.25)"}, …` |  |
| `tunnels` | `{"fill_dash_color": "rgba(255,255,255,0.55)", "toward": "Sand", "towa…` |  |
| `selection` | `{"hover": "#b388ff", "select": "#7c4dff", "casing": "#000000", "opaci…` |  |
| `data` | `{"nodata": "#cccccc", "color_table": "#bbbbbb", "opacity": 0.9, "casi…` |  |
| `overlays` | `{"color": "#6aa9ff", "circle_stroke": "#ffffff", "fill_opacity": 0.15…` |  |
| `boundary` | `{"color": "#6a0dad", "opacity": 0.9}` |  |
| `background` | `{"light": "#e8e6e1", "dark": "#0e1113"}` |  |
| `access` | `{"private": "#c8c8c8", "bus": "#9db8d9", "pedestrian": "#dddde8", "de…` | access_col: the fill of a road that no mode may use |
<!-- /gen:palette -->

### The settings and the keywords

- **The settings file** (`roadstyle.json`, `$ROADSTYLE_CONFIG`, `use_settings`, `settings=`): `profile`, `palette` and `config`
  (`basemap`, `camera`, `annotations`, `tiles`, `api_keys`). See [The settings file](settings.md#the-settings-file).
- **The keywords of `render_edges`** that change the style (`arrows`, `labels`, `color_by`, `view_3d`, the column names, ...):
  [Every parameter](parameters.md#render_edges).

## The look file

`make_look` (Python: `roadstyle._engine.look`; the browser: `resolveLook`) merges the four parts into one JSON object, the input of
the engine. Its file (`Look.to_json`) is version 2. Its schema is `rust/roadstyle-look/look.schema.json`.

!!! warning "Internal"
    The look file changes with the design of the Rust engine. Make it with `make_look` or `resolveLook`; do not write it by hand.

A look file is the style. It has no page key (`name` of the page, `basemap_switcher`, `sidebar`, `views`, `hover_delay_ms`, ...) and
no API key: the page takes them from its caller. The engine also reads a look of version 1 or 0 (0.25.0's `look.json`), whose `args`
are `render_edges`' keywords.

| Key | Content |
|---|---|
| `schema_version` | 2 |
| `palette`, `settings` | the inputs as given: the palette name, the settings |
| `map` | the map options (what the caller chooses for one map): `columns`, `levels`, `color`, `width`, `roads`, `interaction`, `labels`, `arrows`, `tunnels`, `bridges`, `overlays`, `items`, `boundary`, `base_map`, `output` |
| `roads`, `casing`, `labels`, `arrows`, `bridges`, `tunnels`, `selection`, `data`, `overlays`, `boundary`, `background`, `access`, `camera`, `tiles`, `page`, `palettes`, `active`, `interaction` | the sections: the profile and the palette merged, with the settings over them, and the tables of the resolution (the class styles, the road model, the slots, the arrow image) |
| `base_map` | the base map's part (a duckOSM map's layers, 3D heights, style and images); none with no base map |

## The outputs

The rendering gives three outputs: **the MapLibre style** (the rules), **the road data** (the pieces of the roads with their
values) and, with `render_edges`, **the page** that holds both. The examples below come from Monaco (849 drive edges from osmnx,
simple mode, `view_3d=True`), made with `rs.export_inline(edges)` on 2026-10-23.

### The output of each way

Each way to the browser ([Three choices for the road data](../rust/drawing.md#three-choices-for-the-road-data)) gives other
outputs. The style of each way is one of the forms in [The forms of the output style](#the-forms-of-the-output-style).

#### The default: GeoJSON in one HTML file

```python
rs.render_edges(edges).save("map.html")
```

| Output | Content |
|---|---|
| `map.html` | one file: the live style with the road data inline as GeoJSON (gzipped with `compress=True`), MapLibre and the dashboard |

The style: **inline** and **live**. The browser loads the whole file; MapLibre cuts the GeoJSON into tiles itself.

#### Way A: vector tiles in one HTML file

```python
rs.render_edges(edges, tiles=True).save("map.html")
```

| Output | Content |
|---|---|
| `map.html` | one file: the live style, a PMTiles archive of all the tiles (base64 in the page), a side table, MapLibre and the dashboard |

- The style: **tiled** and **live**. Its source `roads` is `{"type": "vector", "url": "pmtiles://roads"}`, and the page reads it
  from the archive inside the file.
- The side table (`window.RS_SIDE`) holds every column of every road, for the popups and for `rs.query`, because a tile holds
  only the columns that the style needs.
- The browser loads the whole file; MapLibre decodes only the tiles in view.

#### Way B: vector tiles on a server

```python
rs.export_style(edges, "out", base_url="https://example.org/map")                     # XYZ folder
rs.export_style(edges, "out", base_url="https://example.org/map", format="pmtiles")   # one PMTiles file
```

| Output | XYZ folder | One PMTiles file |
|---|---|---|
| `style.json` | yes | yes |
| the tiles | `tiles/<z>/<x>/<y>.pbf`, one file for each tile | `roads.pmtiles`, one file |
| the sprite (the one-way arrow) | `sprite.png`, `sprite.json`, `sprite@2x.png`, `sprite@2x.json` | the same |
| the road popup for an app's plugin | `popup.js`, `popup.css` | the same |

- The style: **tiled** and **baked**. Its source `roads` points to `<base_url>/tiles/{z}/{x}/{y}.pbf`, or to
  `pmtiles://<base_url>/roads.pmtiles`. Every address in it starts with `base_url`.
- It has the roads only, with no base map and no page: the map app (GeoLibre, QGIS, a MapLibre page) gives them.
- `export_style` returns the path of `style.json`.

#### Way C: vector tiles made in the browser

```js
const tiler = new Tiler(roads, look, undefined, "Monaco", "rs://1/", ["name", "highway"]);
```

| Output | Content |
|---|---|
| `tiler.style()` | the style, as JSON text |
| `tiler.tile("roads", z, x, y)` | one vector tile (MVT bytes), made when MapLibre asks for it |
| `tiler.props("roads", row)` | the properties of one road, for a click |
| `tiler.archive(bounds, layers)` | only on request: one PMTiles archive of all tiles, as bytes |

- The style: **tiled**, and **live** when the look has `args.state = "live"` (else baked). Its source `roads` points to
  `rs://1/roads/{z}/{x}/{y}`, and the page answers this address with `tiler.tile`.
- Nothing is written to a file. The page can write a whole HTML file with `pageFrom`, as `render_edges` does.

#### Only the style

`rs.export_inline(edges)` (in the browser: `inlineStyle`) gives the style alone, as a dict or JSON text: **inline** and **baked**,
with no page. A map app adds it to its own map.

### The output style

The output style is a [MapLibre style](https://maplibre.org/maplibre-style-spec/) (version 8): one JSON object that MapLibre reads
to draw the roads. It is not the look: the look holds the choices (colors, widths by zoom), and the style holds the rules that
MapLibre applies to each piece at each frame.

#### Its top keys

| Key | Content |
|---|---|
| `version` | `8`, the MapLibre style version |
| `name`, `center`, `zoom` | the map's name (the `name` keyword), the center of the roads and the start zoom |
| `sources` | where the road data is: GeoJSON inside the style, or the address of the vector tiles (next table) |
| `layers` | the drawing rules, in drawing order: each layer takes some features of one source and says how to draw them |
| `glyphs` | the address of the fonts for the street names (MapLibre's font server) |
| `sprite` | the address of the one-way arrow image: only in the tiled style of `export_style`. The inline style gives the image in the metadata (`roadstyle:images`), and the page adds it |
| `state` | only in a live style (the page): the start value of each global state that the controls change (`rs_co`, `rs_top`, `rs_fill_on`, `rs_tun_*`, `rs_palette`; the full look has `rs_colors` and `rs_base` in place of `rs_top`) |
| `metadata` | the `roadstyle:*` keys for the page and the dashboard (below) |

#### Its sources

Each source holds one kind of feature. Inline, each is a GeoJSON source; tiled, there is one vector source `roads`, and each of
these is a layer in its tiles (a layer's `source-layer`).

| Source (or tile layer) | One feature for each | Monaco | Main properties |
|---|---|---|---|
| `roads` | edge (the whole road) | 849 | the class style (`__rs_fill`, `__rs_w`, `__rs_casing`, `__rs_cw`, `__rs_dash`, `__rs_op`), the levels (`__rs_cl`, `__rs_fl`, `__rs_cs`, `__rs_ce`), `__rs_bridge`, `__rs_tunnel`, `__rs_oneway`, `__rs_edge` (its row), and every column of your data |
| `simple` | piece of a road: a casing part, a fill, a bridge shadow, a tunnel dash, an item | 4,607 | `__rs_k` (the kind: 0 casing, 1 fill, 2 shadow, 3 tunnel gap, 4 tunnel dash, 5 item), `r` (the rank: an integer, 100 for each step of the key), `__rs_cap`; the feature id is its road's row, `highway` |
| `slots` | place of a street name or a one-way arrow along a road | 646 | `name`, `oneway`, `slot`, `rank`, `lvl`; the feature id is its road's row |
| `decks` | part of a 3D bridge deck (only with `view_3d=True`) | 588 | `__rs_height`, `__rs_base`, `__rs_edges` |


#### Its layers

The Monaco style has 7 layers, in this drawing order (the first is at the bottom):

| Layer | Type | Source | What it draws |
|---|---|---|---|
| `roads-simple` | line | `simple` | every casing and fill piece of every road, in one layer, sorted by `r * 2^32 + id` |
| `roads-fill` | line | `roads` | (inline export only; not in a tiled style) the whole roads, one line each. Hidden in simple mode (`visibility: none`), where `roads-simple` draws the roads |
| `roads-arrows` | symbol | `slots` | the one-way arrows |
| `roads-labels` | symbol | `slots` | the street names along the roads |
| `roads-highlight` | line | `roads` | (inline export only; not in a tiled style) the glow of a hovered or selected road. Hidden in simple mode, where the pieces of `roads-simple` glow through their feature state |
| `roads-deck-casing`, `roads-bridge-decks` | fill-extrusion | `decks` | the 3D bridge decks |

Each layer has
`metadata["roadstyle:group"]`: `roads`, or the label of an overlay for the layers of an `Overlay`.

#### The rules in a layer

A layer's rules are MapLibre expressions that read the properties of each piece. For example, in `roads-simple`:

- `"line-sort-key": ["+", ["*", ["get", "r"], 4294967296], ["id"]]` draws each piece by its rank and then by its road's row, so a bridge goes over the road under it.
- `"line-color"` picks by the kind: a casing piece (`__rs_k` 0) takes `__rs_casing` (or the bridge casing color on a bridge), a
  shadow (2) a transparent black, a tunnel dash (4) the tunnel color, and so on.
- `"line-width"` interpolates on the zoom for the class of the piece, and `"line-offset"` moves each direction of a two-way road
  to its side.
- A hover or a selection reads the feature state (`["feature-state", "hover"]`, `"select"`), so the glow needs no new style.

A filter (`"filter"`) takes only the features of the layer: for example, `roads-arrows` takes only the slots of one-way roads.

#### The metadata

| Key | In | Content |
|---|---|---|
| `roadstyle:interaction` | every style | the popup fields, the hover tooltip and the hover delay. In `export_style`, also the addresses of `popup.js` and `popup.css` |
| `roadstyle:images` | the inline style | the images that the page adds to the map: the one-way arrow (`oneway`) as a data URL, with `sdf` and `pixelRatio` |
| `roadstyle:color_options` | a map with data colors | the Colour by options and their legends: `[{name, prop, legend}]` |
| `roadstyle:contract`, `roadstyle:state`, `roadstyle:controls` | a live style | the contract version, the start value of each state, and the options of the dashboard |
| `roadstyle:planner`, `roadstyle:planner_skipped` | a map with mapstyle's route planner | the planner's graphs |

The full list of names, with the code that writes and reads each one: [The interaction contract](contract.md).

#### The forms of the output style

Two separate choices give the form of a style.

**Where the data is:**

| Form | Made by | Sources |
|---|---|---|
| **Inline** | `export_inline`, `inlineStyle`, `render_edges` | GeoJSON sources with all the data inside the style |
| **Tiled** | `export_style` (`style.json`), `tiler.style()`, `render_edges(tiles=True)` | one vector source `roads` with the address of the tiles: `<base_url>/tiles/{z}/{x}/{y}.pbf`, `pmtiles://...` or `rs://...`; zooms 6 to 18 |

**Whether the controls can change it:**

| State | Made by | Content |
|---|---|---|
| **Baked** (the default) | `export_inline`, `export_style`, and the browser calls without `state` | the start values written into the expressions. The colors and the tunnel look are fixed; the hover and the filters still work |
| **Live** | `render_edges` (the style inside the page), or the look's `args.state = "live"` | the `state` block and `["global-state", ...]` in the expressions, and the metadata `roadstyle:contract`, `roadstyle:state` and `roadstyle:controls`, so the dashboard changes the map at run time |

### The road data

The road data is the features of the four sources above, with their properties. It is in one of two forms
([Three choices for the road data](../rust/drawing.md#three-choices-for-the-road-data)):

- **GeoJSON** inside the style (`sources.<name>.data`).
- **Vector tiles** (Mapbox Vector Tile 2.1): one source `roads`, with the tile layers `simple`, `slots`, `decks` and the base map's layers (no `roads` tile layer since 2026-10-27: a click reads the road's row in `props.json` of `export_style`, or in the road table of a page; the popup fields of an overlay are in `props/<source>.json` of `export_style`, by row, not in its tiles), zooms
  6 to 18 and a buffer of 80 units. A feature's id is its index in its source. A piece of the layer `simple` and a slot have their road's row as their id (all
  pieces of a road share it). A tile keeps the keys of the layer's one set (the keys that the style reads, the page's keys, the 3 filter keys
  and the columns named in `keep`), but not a `__rs_*` flag that is false: every reader takes a missing flag as false. Below the last zoom, a line is
  simplified to half a tile unit.

Each piece carries its values as `__rs_*` properties, and the style's rules read them
([The rules are in the style, the values are in the data](../rust/drawing.md#the-rules-are-in-the-style-the-values-are-in-the-data)).
The road fields are in the source `roads` (GeoJSON) or in the side table (tiles). One road table for both forms is planned:
[The three stages and the one call](../rust/architecture.md#the-three-stages-and-the-one-call).

### The page

`render_edges` and `pageFrom` write one HTML file. It holds:

- the live style, with the data inline (gzipped, `compress=True`) or with the PMTiles archive (`tiles=True`);
- MapLibre GL JS 5.24 (inside the file, or from a CDN);
- the dashboard: the modules of `static/dashboard/` as one script, the popup (`popup.js`, `popup.css`) and `dashboard.css`;
- the options of the dashboard: the object `RS_OPTIONS`, with the values of the page keywords and the camera (`camera`).

The file opens from disk. It needs a server only for Street View and Google 3D.

**See also:** [Every parameter](parameters.md) · [Settings & palettes](settings.md) · [Which road is on top](../guides/levels.md)
