# Every parameter

<p class="lead">Every public name and every keyword, grouped, with its default. Use it as a lookup.</p>

## Public API

Everything in `roadstyle.__all__`, as `import roadstyle as rs; rs.<name>`.

| name | returns | what |
|---|---|---|
| **Render** | | |
| `render_edges(gdf, **kw)` | `WebMap` / `folium.Map` / `lonboard.Map` | the main call; every keyword [below](#render_edges) |
| `render_dashboard(gdf, **kw)` | `WebMap` | map + query sidebar ([Pages](#pages)) |
| `render_report(gdf, **kw)` | `WebMap` | map + stats sidebar ([Pages](#pages)) |
| `render_street_view(gdf, **kw)` | `WebMap` | map + Google Street View side by side ([Pages](#pages)) |
| `sidebar_html(name)` | `str` | a bundled sidebar fragment: `"dashboard"`, `"report"`, `"street_view"` |
| `snapshot(map_or_html, out_path, *, center, zoom, pitch, bearing, width=1200, height=800, scale=1, settle=2.5, timeout=40)` | path | a PNG via headless Chromium (needs `playwright`) |
| **Read your data** | | |
| `RoadEdges` | | the canonical input: EPSG:4326 lines + a class column |
| `as_edges(data, *, class_col="highway")` | `RoadEdges` | coerce any input below (`render_edges` does this for you) |
| `normalize_edges(gdf, *, class_col, rename)` | `RoadEdges` | from a GeoDataFrame |
| `load_edges(path, *, class_col, layer, rename)` | `RoadEdges` | from any geo file (`layer` for GPKG) |
| `from_geojson(obj, *, class_col, crs=4326, rename)` | `RoadEdges` | from a GeoJSON mapping or a `to_spec` dict |
| `from_arrow(table, *, class_col, geometry, crs, rename)` | `RoadEdges` | from a pyarrow Table |
| `from_duckdb(con_or_rel, query=None, *, geometry, class_col, crs=4326, rename)` | `RoadEdges` | from DuckDB; select the geometry as `ST_AsWKB(geom)` |
| `filter_edges(gdf, include, exclude, highway_col, match_links)` | GeoDataFrame | keep / drop road classes |
| `highway_types(gdf, highway_col="highway", normalize=True)` | `list` | the classes present |
| **roadstyle.js / JSON output** ([Put it on a website](../guides/website.md)) | | |
| `to_spec(gdf, **kw)` | `dict` | data + baked style + legend + metadata |
| `to_geojson(gdf, **kw)` | `dict` | the styled FeatureCollection only |
| `to_html(gdf_or_spec, *, full=True, div_id="rsmap", width="100%", height="500px", **kw)` | `str` | a full roadstyle.js page, or a `<div>+<script>` fragment (`full=False`) |
| `to_iframe(gdf_or_spec, *, width="100%", height="500px", **kw)` | `str` | a self-contained `<iframe srcdoc=…>` |
| `save(gdf_or_spec, path, **kw)` | | write the roadstyle.js page |
| `save_spec(spec_or_gdf, path, **kw)` / `load_spec(path)` | / `dict` | the spec to / from a `.json` file |
| **Stylers** ([below](#stylers)) | | |
| `ClassStyler`, `CategoricalStyler`, `NumericStyler`, `ColorTableStyler` | | how each edge's colour and width is chosen |
| `color_by_class`, `color_by`, `color_by_value` | styler | shortcuts for the first three |
| `build_styler(**kw)` | styler | picks a styler from `render_edges`-style keywords |
| `Styler`, `ResolvedFrame` | | the styler protocol and its output (per-edge style arrays) |
| **Palettes, base maps, settings** ([Settings & palettes](settings.md)) | | |
| `PALETTES`, `HIGHSAT`, `CARTO` | `dict` | the palette registry and two of its tables |
| `RoadStyle(fill, width, casing_width, casing="#bcbcbc", dash=None, opacity=1.0)` | | one class's look |
| `SELECTION` | `dict` | the selection colours (`core`, `glow`, `glow_opacity`, `casing`) |
| `register_palette`, `save_palette`, `load_palette`, `palette_to_dict`, `palette_from_dict` | | add palettes, palette JSON I/O |
| `BASEMAPS`, `Basemap`, `get_basemap`, `register_basemap` | | base maps ([below](#basemap)) |
| `BaseLayerSwitcher` | folium element | the folium base-map switcher |
| `set_api_key(key, provider=None)` / `get_api_key(provider=None)` | / `str` | base-map API keys |
| `StyleConfig` | | global styling knobs ([below](#styleconfig)) |
| `use_settings(*sources)` | | apply settings (path or dict) for the process; no argument drops them |
| `Overlay` | | an extra layer for the web backend ([below](#overlay)) |
| **Helpers** | | |
| `compute_levels(edges, band_col=None, order="priority", ...)` | edges + 4 columns | the level step in one call (`near_rules=False`: set True to also lift parts that only come near; `head_m` decides once which parts of a stack cross, see [design](../design/level_input.md)): `casing_start`, `casing_level`, `casing_end`, `fill_level` ([design](../design/level_input.md)) |
| `level_input(edges, id_col="edge_id", ...)` | `(roads, pairs)` | the solver's input from any edges: one row per road, one row per relation (`meet`, `stack` one row per crossing part of the upper road, `order`; `near` with `near_rules=True`); `head_m` / `heads` (a heads.csv table) decide which parts cross |
| `solve_levels(roads, pairs, edits=None, ...)` | roads + 4 columns | the solver, from the tables only (a stack: one row per part, `a_end` start / main / end); `edits` switch rows off or add them; `fixed` (`{road: (casing_start, casing_level, casing_end, fill_level)}`) holds those roads' numbers and solves the others (the editor's local re-solve) |
| `level_area.make_area(edges, folder, db=None, ...)` / `level_area.solve_area(folder)` | `(roads, pairs)` / solved roads | an area folder (`roadstyle-levels make` / `solve`); with `db` every solve also writes into that DuckDB file |
| `save_area_levels(con, folder)` / `load_area_levels(con, edges)` | – / edges + 8 columns | an area's result into `visualization.edge_levels` and back (the four numbers and each edge's ends); reading checks the edges |
| `resolve(highway, palette, tunnel, bridge)` | `ResolvedStyle` | one edge's resolved style |
| `base_style(highway, palette="amber")` | `RoadStyle` | the palette entry for a class |
| `selection_style(base_width=4.0)` | `dict` | the selection profile scaled to a width |
| `normalize_highway(value)` | `(base, is_link)` | strip OSM `_link` |
| `make_legend(spec, position="bottomleft")` | folium element | a folium legend from a `ResolvedFrame.legend` |

A `WebMap` has `.html` (the page as a string), `.save(path)`, and shows inline in a notebook (Jupyter Notebook 7, JupyterLab): the
preview loads the bundled MapLibre version (5.24) from the jsDelivr CDN instead of inlining it, so it needs the network.

## `render_edges`

`render_edges(gdf, **kw)`: `gdf` is a GeoDataFrame (LineStrings + a `highway` column, any CRS) or
a `RoadEdges`. Every keyword is optional. **Backends** says which renderers read it; the others
ignore it.

### Look

| keyword | default | backends | what |
|---|---|---|---|
| `backend` | `"web"` | | `"web"` (MapLibre, one offline file), `"folium"`, `"lonboard"` ([Big networks](../guides/big-networks.md)) |
| `palette` | `"amber"` | all | `"amber"` (orange to green main roads, slate-grey streets), `"carto"` (soft OSM Carto tones), `"highsat"` (bright), `"mono"` or a registered palette |
| `basemap` | the `basemap` setting (`"voyager"`) | all | a `BASEMAPS` key, a `Basemap`, a `{z}/{x}/{y}` URL or an xyzservices provider |
| `basemaps` | web: `esri_gray`, `positron`, `osm`, `satellite`, `voyager`, `dark_matter`, `blank` | web, folium | the base maps offered in the switcher |
| `basemap_switcher` | `True` | web | the base-map button (a map control, last in the top-right column) and its menu; `False` with a `basemaps=` list keeps them for `rsSetBasemap` |
| `zoom_readout` | `True` | web | the small "z 13.2" zoom level beside the scale bar; `False` leaves it out |
| `api_key` | `None` | all | key for a keyed tile provider ([order](settings.md#base-maps-api-keys)) |
| `arrows` | `True` | web | one-way chevrons along each one-way edge |
| `labels` | `True` | web | curved street names from the `name` column |
| `legend` | `True` | web, folium | a legend for data colouring (class styling has none) |
| `legend_position` | `"bottomleft"` | folium | legend corner |
| `name` | web `"roadstyle"`, folium `"roads"` | web, folium | page title (web) / layer name (folium) |
| `hover_color` / `select_color` | `"#b388ff"` / `"#7c4dff"` | web | highlight of the hovered / selected road |
| `minzoom` | `None` | web | hide minor classes when zoomed out: `True` = the `minzoom` setting, a dict overrides parts, `None` = all classes at all zooms |
| `offset_frac` | `0.28` | web | two-way lane offset, fraction of the road's pixel width; `0` = no lane split |
| `width_frac` | `0.6` | web | each lane's width, fraction of the full road width |
| `offset_zoom` | `15` | web | zoom where the two directions start to fan apart |
| `settings` | `None` | all | a settings override for this call only: a dict, or the path of a JSON or YAML file; a file that cannot be read is an error ([levels](settings.md#settings-levels)) |

### Filtering

| keyword | default | backends | what |
|---|---|---|---|
| `include` / `exclude` | `None` | all | keep only / drop these classes (str or list) |
| `match_links` | `True` | all | `primary` also matches `primary_link` |
| `filter_control` | `True` | web, folium | the road-class filter panel (folium: only when there is no legend) |
| `filter_col` | `None` | web | the column the filter panel lists, when it differs from `highway_col` |

### Colour by data

| keyword | default | backends | what |
|---|---|---|---|
| `color_by` | `None` | all | colour by this column instead of road class |
| `colors` | `None` | all | categorical `{value: hex}`, or `"self"` = the value is the colour |
| `cmap` | `"viridis"` | all | numeric ramp: a branca / matplotlib name (`"RdYlGn_r"`) or a list of hex stops |
| `vmin`, `vmax` | data min / max | all | ramp range |
| `width_by` | `None` | all | `(min_px, max_px)`: width follows the numeric value |
| `color_table` | `None` | all | per-edge colour: `{id: colour}`, a Series, or a DataFrame; missing edges grey, class widths kept |
| `color_key` | `"edge_id"` | all | the edges column matched against `color_table` |
| `color_col` | `"color"` | all | the colour column when `color_table` is a DataFrame |
| `style` | `None` | all | a styler object; overrides `palette` / `color_by` |
| `color_options` | `None` | web | `{name: {styler kwargs}}`: a *Colour by* menu that recolours in the browser; the first entry shows on open |
| `color_active` | `0` | web | the option shown on open (index or name) |
| `views` | `None` | web | `{name: {setting: value}}`: a *View* menu next to *Colour by*; each view sets several things at once, the first shows on open |

Each `color_options` value takes `color_by`, `colors`, `cmap`, `vmin`, `vmax`, `width_by`,
`palette`, `style`, `missing`; `{}` is the class style. See [Colour by your data](../guides/colour.md).

A `views` entry sets only what it names: `color` (a `color_options` name), `road_fill`, `bridges`, `tunnels`, `view3d`
(`True` / `False`), `overlays` (`{label: True / False}`), `classes` (a list of road classes), `basemap` (a key). An unknown
setting, or a name the page does not have, is an error.

### Popups & hover

| keyword | default | backends | what |
|---|---|---|---|
| `road_popup` | `True` | web | on click: `True` = `name`, `edge_id`, `edge_ref`, `highway`, `lanes`, `bridge`, `tunnel`; a list = those columns; `"all"`; `"panel"` = docked panel; `False` = none (`rs:select` still fires) |
| `popup_mode` | `None` (= `"popup"`) | web | `"panel"` docks the read-out in a side panel with a search box |
| `road_tooltip` | `False` | web | on hover: `True` = every column, a list = those columns |
| `hover_delay_ms` | `300` | web | the road tooltip shows once the mouse rests this long on a road (a passing mouse shows none); the hover highlight follows at once; `0`: at once |
| `tooltip` | `None` | web, folium | hover columns. Web: alias of `road_tooltip`, `None` = no tooltip. Folium: `None` = all columns |
| `selected` | `None` | folium | a GeoDataFrame of edges to highlight (web: use `rsHighlight` / `rsColor`) |
| `copy_field` | `"edge_id"` | folium | click copies this column's value; `None` = off |

### Street View

| keyword | default | backends | what |
|---|---|---|---|
| `street_view` | `"window"` | web | `"window"` = a map button and a floating window that follows the clicked road; `True` = a link in the popup; `False` = none. Needs the page served over http(s) ([guide](../guides/street-view.md)) |
| `street_view_key` | `None` | web | a Google Maps JavaScript API key for the window: its bar offers Linked (a panorama; the map marker walks with the viewer) and Classic (the embed). Written into the page; restrict it to your site's addresses |

### Camera & 3D

| keyword | default | backends | what |
|---|---|---|---|
| `pitch` / `bearing` | the `camera` setting (`0` / `0`) | web | starting tilt / rotation in degrees |
| `view_3d` | `False` | web | open tilted to `camera.pitch_3d`, with raised 3D bridge decks |

### Output & scale

| keyword | default | backends | what |
|---|---|---|---|
| `tiles` | `False` | web | pack the roads, the casing pieces and the end caps as embedded PMTiles (for ~10⁵ edges); needs `roadstyle[tiles]` |
| `simple` | `True` | web | draw every road piece (the casings, cut into their heads, and the fills, every position) in ONE line layer, ordered by `line-sort-key` as the full look orders its layers, colour and width per feature: much faster to load and zoom on a big page. A bridge's casing is `bridge_casing_extra` px wider each side than in the full look, and its shadow lies evenly around its main part (blurred, not offset); both grow with the zoom: below zoom 14 no shadow and the full look's bridge casing, from 17 the full extra width and shadow. A tunnel's casing is two pieces (the palette's gap colour, then the dashes on top, `tunnel_casing_dash`), a dashed class's fill has its dash pattern, and each road's end shapes (`cap_col`, `cap_start_col`, `cap_end_col`) are drawn per piece (needs MapLibre 5.22, the bundled one; the notebook preview loads the same version). Leaves out the twin end caps. Street names and one-way arrows are one layer each, drawn above all roads (a name of a road under a bridge can show on the bridge); the items of `Overlay(edge_col=...)` too. With `tiles=True` the pieces are a tile layer of the archive; `tunnel_control=True` works, with its palette and dash-ratio selects. `simple=False` is the full look: dashes, square and flat ends, the offset shadow) |
| `compress` | `True` | web | gzip the inlined data; `False` = plain JSON |
| `tunnel_control` | `False` | web | on a map with tunnels, a *Tunnels* box (a tool for choosing the look): the colour list (`tunnel_toward`), the tunnel slider (`tunnel_strength`: 0, 25, 50, 55, 60, 65, 70, 75, 100), the casing palette and the dash ratio ([design](../design/tunnel_look.md)) |
| any other keyword | | folium | passed to `folium.Map(...)` (e.g. `location`, `zoom_start`) |

Returns a `WebMap` (web, `.save()`), a `folium.Map` (`.save()`) or a `lonboard.Map` (`.to_html()`).

### Column mapping

| keyword | default | backends | what |
|---|---|---|---|
| `highway_col` | `"highway"` | all | the road-class column (widths, casing, draw order) |
| `tunnel_col` / `bridge_col` | `"tunnel"` / `"bridge"` | all | tunnels draw under (faded, two-tone dashed casing), bridges on top |
| `layer_col` | `"layer"` | web | OSM `layer`; negative sinks an edge when there is no tunnel/bridge column |
| `casing_start_col` / `casing_end_col` / `head_m` | `None` / `None` / `5.0` | web | with the level columns: the casing is divided into a start head, a main part and an end head. The two columns hold the casing numbers of the heads (the main number is `casing_level_col`); `head_m` is the length of each head in metres. An edge at least `2 · head_m` long whose three numbers differ is drawn as three casing pieces, each at its own number; the fill stays one line ([design](../design/levels_split_casing.md#9-the-renderer)) |
| `head_start_m_col` / `head_end_m_col` | `None` | web | an edge's own head lengths in metres (`solve_levels`' `head_start_m` / `head_end_m`); null = `head_m`. A road shorter than its two heads is cut in their ratio |
| `road_fill` | `True` | web | `False`: draw the casing of each road but not its fill (the fill layers stay, invisible, for clicks); the items attached with `Overlay(edge_col=...)` are the fill |
| `edge_id_col` | `"edge_id"` | web | the column with the id of each edge, the ids that an overlay's `edge_col` refers to |
| `casing_level_col` / `fill_level_col` | `None` | web | two integer columns: the position in the drawing order of an edge's casing and of its fill (0 = ground); at each position casings first, then fills; one layer pair per position; the position alone decides (a bridge too). Not given: `render_edges` computes them with `rs.compute_levels(edges)` and its defaults; `render_edges` takes no `band_col` or `order` (the level step: [guide](../guides/levels.md), [design](../design/level_input.md)) |
| `cap_col` | `None` | web | a column of true / false: true draws the edge with square ends (butt caps) instead of round ones, for a road drawn in pieces that meet without a ring; `"square"` = flat but as far past the end as a round end (the drawn length kept); null / false = round ends |
| `cap_start_col` / `cap_end_col` | `None` | web | one end each, same values as `cap_col` (and `"round"`); null = `cap_col`'s. An edge whose two ends differ is drawn from its casing heads and two fill halves (position mode) |
| `width_m_col` | `None` | web | a column of widths in metres (a lane, a road with a `width` tag, a canal): from `width_m_zoom` on the line is drawn exactly that wide, its casing inside; null = the class width |
| `width_m_zoom` | `16` | web | the zoom from which `width_m_col` widths apply; below it, the class widths (so a narrow line doesn't vanish zoomed out) |
| `casing_m` | `0.15` | web | with `width_m_col`: the casing on each side, in metres, inside the width (two lines side by side show a `2 × casing_m` divider) |
| `directed_col` | `None` | web | a column: true / null = the edge is a direction of travel of its own, false = undirected (a footway stored both ways, a one-way street's walking-only reverse). An edge and its reverse are two lanes only when neither is false; otherwise one line, centred and full width |

### Overlays & boundary

| keyword | default | backends | what |
|---|---|---|---|
| `overlays` | `None` | web | a list of [`Overlay`](#overlay): zones, points, lines |
| `boundary` | `None` | web | a dashed outline on top: shapely geometry, GeoDataFrame or GeoJSON |

## Pages

Web-only page builders. Each takes every `render_edges` keyword and returns a `WebMap`; they only
change the defaults below.

| function | page | changed defaults | own keywords |
|---|---|---|---|
| `render_dashboard` | map + sidebar: base map and colour-by menus, class filter with legend, query box, results table, read-out | `name="Roads dashboard"`, `basemap_switcher=False`, `filter_control=False`, `road_popup=False` | |
| `render_report` | map + sidebar: KPI cards, colour-by legend, filter, search, read-out | `name="Roads report"`, `filter_control=False`, `road_popup=False` | |
| `render_street_view` | map + Google Street View of the clicked road | `name="Roads and Street View"`, `road_popup=False`, `street_view=True` | see below |

| `render_street_view` keyword | default | what |
|---|---|---|
| `layout` | `"beside"` | `"beside"` = Street View right of the map, `"below"` = under it |
| `panel_width` | `42` | Street View's share of the window, 20-80 % (of the height when below) |
| `resizable` | `True` | a divider the viewer can drag; the choice is remembered in their browser |
| `street_view_key` | `None` | a Google Maps JavaScript API key: the panel becomes a real panorama, the map marker walks and turns with the viewer, and it shows Google's own street imagery only. Written into the page; restrict it to your site's addresses |

## Stylers

`render_edges` builds a styler for you. Build one yourself and pass it as `style=` for full control.

| styler | field | default | what |
|---|---|---|---|
| `ClassStyler` | `column` | `"highway"` | the class column |
| | `palette` | `"amber"` | name or `{class: RoadStyle}` |
| | `normalize_links` | `True` | draw `*_link` as the parent class, narrower |
| | `fallback` | `"unclassified"` | class for unknown values |
| | `tunnel_col` / `bridge_col` | `None` | tunnel / bridge columns |
| | `config` | the settings | a `StyleConfig` |
| `CategoricalStyler` | `column` | | the category column |
| | `colors` | `{}` | `{value: hex}` |
| | `fallback_color` | `"#cccccc"` | unmapped / missing values |
| | `missing` | `"base"` | in `color_options`: unmapped edges keep the base fill (`"base"`) or use `fallback_color` (`"self"`) |
| | `width` | `2.0` | px, or a column name |
| | `casing`, `casing_width` | `None`, `0.0` | optional constant casing |
| | `opacity`, `casing_opacity` | `0.9`, `0.75` | |
| | `dash` | `None` | `(on, off)` px |
| `NumericStyler` | `column` | | the numeric column |
| | `cmap` | `"viridis"` | ramp name or list of hex stops |
| | `vmin`, `vmax` | data min / max | |
| | `width`, `width_by`, `width_column` | `2.0`, `None`, `None` | constant width, or `(min, max)` px over the value of `width_column` (default `column`) |
| | `nan_color` | `"#cccccc"` | missing values |
| | `missing` | `"base"` | as for `CategoricalStyler`, with `nan_color` |
| | `casing`, `casing_width`, `opacity`, `casing_opacity` | `None`, `0.0`, `0.9`, `0.75` | |
| `ColorTableStyler` | `color_column` | required | a column of colours, one per edge |
| | `highway_col`, `palette` | `"highway"`, `"amber"` | where widths and casing come from |
| | `fallback_color` | `"#bbbbbb"` | blank or invalid colours |

## Overlay

`rs.Overlay(data, ...)`: your own geometry, drawn with one flat style (web only). Defaults come from
the `overlays` setting. See [Add your own layers](../guides/overlays.md).

| field | default | what |
|---|---|---|
| `data` | required | GeoDataFrame, GeoSeries or GeoJSON (any CRS) |
| `kind` | auto | `"fill"`, `"line"`, `"circle"`; auto from the geometry |
| `placement` | `"over"` | `"under"` or `"over"` the roads |
| `color` | `"#6aa9ff"` | paint colour |
| `opacity` | fill `0.15`, circle `0.85`, line `0.9` | |
| `outline` | `color` | polygon outline colour |
| `radius` | `6` | circle radius, px |
| `width` | `2` | line / outline width, px |
| `label` | `"Layer N"` | name in the *Layers* control, and the `layer` argument of the JS API |
| `popup` | `None` = all fields | fields on click; `[]` = not clickable |
| `tooltip` | `None` | fields on hover |
| `visible` | `True` | shown on open |
| `edge_col` | `None` | the property with the id of the feature's edge: the overlay is attached to edges, drawn at its edge's fill number (the guide: [Overlays](../guides/overlays.md#overlays-attached-to-edges)) |
| `order_col` | `None` | with `edge_col`: the property with the feature's order (whole number, lower first; null = 0) |
| `select` | `"road"` | with `edge_col`: a hover or click picks the feature's road (`"road"`) or the feature itself (`"item"`: its own highlight and popup, `rs:select` with `item` and the road); anything else is an error |
| `color_col` | `None` | the property with a colour per feature (null: `color`) |
| `style` | `None` | the name of a style in the settings `config.overlays.styles` (a library's theme); its fields fill what the overlay does not give |
| `width_m` | `None` | a line's width in metres, exact from `min_zoom` on (replaces `width`) |
| `dash` | `None` | a line's dash pattern in line widths, `[3, 3]` |
| `min_zoom` / `max_zoom` | `None` | the zooms in which the overlay is drawn |
| `text_col` / `text_size` / `text_color` / `text_halo` | `None` | `kind="text"`: the property with the text, its size (px), colour and halo colour |

## Basemap

`rs.Basemap(key, label, url, attr, ...)`: one tile source. Register it with `rs.register_basemap`.
Built-ins: [Settings & palettes](settings.md#base-maps-api-keys).

| field | default | what |
|---|---|---|
| `key` | required | short id, e.g. `"mytiles"` |
| `label` | required | name in the switcher |
| `url` | required | `{z}/{x}/{y}` template; `""` = no tiles (plain canvas, fully offline) |
| `attr` | required | attribution |
| `is_dark` | `False` | a dark canvas |
| `satellite` | `False` | apply the satellite colour filter |
| `lonboard` | `None` | the matching lonboard base map name |
| `bg`, `preview`, `subdomains` | `"#444"`, three greys, `"abc"` | switcher thumbnail, tile subdomains |
| `maxzoom` | `19` | the provider's last zoom level with real tiles; zoomed in further, the map scales that level up instead of showing missing tiles. Built-ins: Esri grey maps 16, CARTO 20, the rest 19; xyzservices providers bring their own `max_zoom` |

## StyleConfig

The `config` block of the settings. Change it in a [settings override](settings.md), not in code.

| field | default | what |
|---|---|---|
| `fill_opacity` / `casing_opacity` | `0.9` / `0.75` | line opacities |
| `casing_extra` | `2.0` | reserved (palettes set casing widths) |
| `link_scale` | `0.7` | `*_link` width relative to the parent |
| `tunnel_opacity_scale` | `0.45` | tunnel fade |
| `tunnel_casing_dash` | `[1, 1]` | the tunnel casing's dash and gap, in line widths; a tunnel's casing is its dash layer alone |
| `tunnel_strength` | `60` | the tunnel look, v2's slider (0-100): everything on a tunnel (fill, names, arrows, attached items) moves toward the `tunnel_toward` colour. Opaque, no see-through. The Tunnels box has the steps 0, 25, 50, 55, 60, 65, 70, 75, 100 |
| `tunnel_toward` / `tunnel_towards` | `Sand` / eight | the colour a tunnel moves toward: a name in `tunnel_towards` (`name: "#rrggbb"`: Slate `#64748b`, Dark `#14181d`, Light `#efede8`, Graphite `#374151`, Navy `#1e293b`, Stone `#78716c`, Sand `#d6cfc4`, Teal `#134e4a`) or any `#rrggbb`; the same for every base map. An unknown name or a bad colour is an error naming the choices |
| `tunnel_palette` / `tunnel_palettes` | `Graphite + silver` / seven | the tunnel casing: a pattern of two colours as they are (the default `Graphite + silver`), or `One colour` (slate dashes, empty gaps); `name: [dash, gap]` (`Slate + ice`, `Blue + cyan`, `Warm + sand`, `Graphite + silver`, `Indigo + lavender`, `Teal + mint`); an unknown name is an error |
| `tunnel_fill_dash` / `tunnel_fill_dash_color` | `[]` (none; e.g. `[1.2, 1.2]`) / `rgba(255,255,255,0.55)` | light dashes along a tunnel's fill, over any road colour (`[]` = none); a dashed class (steps, a dashed path) keeps only its own dashes |
| `single_line_classes` | footway, path, steps, pedestrian, cycleway, track, bridleway, corridor, platform | a two-way pair (two reverse edges) of these classes is drawn as ONE line at full width, once, not as two lanes (a footway as two thin dashed lines looked wrong); both edges keep their data, a click shows both directions. `[]` = every pair is lanes |
| `twin_end_caps` | `true` | a two-way road ends like one road: one road-wide round cap under its two lanes at each end, where both lanes have the same colour (`false` = each lane's own round end) |
| `twin_casing` | `"one"` | a two-way road given as two directed edges: `"one"` = ONE casing around both directions, at the road's full width (a direction's casing + twice its offset), drawn once from the first edge's casing pieces (numbers, heads, caps; the twins must agree reversed, else a warning names the pair), each direction keeping its own fill; the end caps are the casing's own (no `twin_end_caps` blob); a pair's dead end (no other edge has an end point there) is square for the casing and both fills unless a cap column gives it a cap. The bridge shadow and the tunnel dashes follow it. `"each"` = each direction its own casing, half the width, shifted (the look before 2026-10-08) |
| `bridge_casing_m` / `bridge_casing_px` | `0.25` / `1.0` | with metre widths (`width_m_col`): a bridge's deck casing is at least this wide each side in metres, whatever `casing_m` is, and never thinner than this many pixels each side at any zoom (metres are sub-pixel zoomed out), so the bridge look shows on lines with no casing |
| `bridge_casing_extra` / `bridge_casing_color` | `1.5` / `"#64748b"` (slate) | bridge casing, px wider / colour |
| `bridge_shadow` / `bridge_shadow_color` / `bridge_shadow_blur` / `bridge_shadow_offset` | `true` / `rgba(0,0,0,0.25)` / `4` / `[2, 2]` (and `bridge_shadow_trim_m` `3`: no shadow over the last 3 m where a bridge comes down) | a soft shadow under a bridge: a line per stretch at the lowest casing number of its edges, straight on through a junction where the numbers agree; none where the bridge comes down (position mode): px of blur, px shifted right and down (lit from the top left) |
| `minor_no_casing` | cycleway, footway, living_street, path, pedestrian, service, track | classes drawn without casing |
| `minzoom` | motorway 4 … residential 13 … footway 15 | class → hidden below this zoom, with `minzoom=True` |
| `basemap` | `"voyager"` | the default base map |
| `labels` | `color #5b5b5b`, no halo | street-name paint |
| `arrows` | `color #5b5b5b`, `opacity 0.7` | one-way chevron paint |
| `camera` | `pitch 0`, `bearing 0`, `pitch_3d 55`, `max_pitch 70` | starting camera and 3D tilt |
| `bridge_decks` | `base_m 5`, `thickness_m 1`, `ramp_m 40`, `step_m 2.5`, `match_zoom 18`, `opacity 0.7`, `width_scale 0.6`, `flat_below 16`, `casing_px 2` | 3D bridge decks |
| `overlays` | `color #6aa9ff`, `radius 6`, `width 2`, per-kind opacities, `circle_stroke #ffffff` | `Overlay` defaults |
| `annotations` | `slot_m 100` | label / arrow spacing along a road, metres |
| `tiles` | `minzoom 6`, `maxzoom 15`, `extent 4096`, `buffer_px 80` | the `tiles=True` tileset |
| `api_key` / `api_keys` | `None` / `{}` | default key / per-provider keys |

**See also:** [JavaScript API](javascript.md) · [Settings & palettes](settings.md) · [Command line](cli.md)
