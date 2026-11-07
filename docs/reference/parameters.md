# Every parameter

<p class="lead">Every public name and every keyword, grouped, with its default. Use it as a lookup.</p>

## Public API

Everything in `roadstyle.__all__`, as `import roadstyle as rs; rs.<name>`.

| name | returns | what |
|---|---|---|
| **Render** | | |
| `render_edges(gdf, **kw)` | `WebMap` | the main call; every keyword [below](#render_edges) |
| `render_dashboard(gdf, **kw)` | `WebMap` | the map, a panel and the standard toolbox ([Pages](#pages), [Dashboard options](#dashboard-options)) |
| `render_street_view(gdf, **kw)` | `WebMap` | map + Google Street View side by side ([Pages](#pages)) |
| `sidebar_html(name)` | `str` | a bundled sidebar fragment: `"dashboard"`, `"street_view"` |
| `export_style(gdf, out_dir, *, base_url, format="xyz", **kw)` | path of `style.json` | the roads as a MapLibre style, vector tiles (`"xyz"` folder or `"pmtiles"`) and a sprite, for other map apps ([guide](../guides/website.md#a-style-for-other-map-apps)). The style has the roads only: `basemap=`, `views=` and `color_active=` are errors. `kw` go to `render_edges` |
| `export_look(path=None, *, profile=None, palette=None, edges=None, highway_col="highway", oneway_col="oneway", tunnel_col="tunnel", bridge_col="bridge", id_col="edge_id", positions=None)` | the look (dict) | MapLibre layers with no source, for a data layer in another app (the GeoLibre plugin). It makes one casing layer and one fill layer for each drawing position (`positions`, else those of `edges`, else -10 to 10) |
| `snapshot(map_or_html, out_path, *, center, zoom, pitch, bearing, width=1200, height=800, scale=1, settle=2.5, timeout=40)` | path | a PNG via headless Chromium (needs `playwright`) |
| **Read your data** | | |
| `RoadEdges` | | the canonical input: EPSG:4326 lines + a class column |
| `as_edges(data, *, class_col="highway")` | `RoadEdges` | coerce any input below (`render_edges` does this for you) |
| `normalize_edges(gdf, *, class_col, rename)` | `RoadEdges` | from a GeoDataFrame |
| `load_edges(path, *, class_col, layer, rename)` | `RoadEdges` | from any geo file (`layer` for GPKG) |
| `from_geojson(obj, *, class_col, crs=4326, rename)` | `RoadEdges` | from a GeoJSON mapping |
| `from_arrow(table, *, class_col, geometry, crs, rename)` | `RoadEdges` | from a pyarrow Table |
| `from_duckdb(con_or_rel, query=None, *, geometry, class_col, crs=4326, rename)` | `RoadEdges` | from DuckDB; select the geometry as `ST_AsWKB(geom)` |
| `filter_edges(gdf, include, exclude, highway_col, match_links)` | GeoDataFrame | keep / drop road classes |
| `highway_types(gdf, highway_col="highway", normalize=True)` | `list` | the classes present |
| `classify(values, method="natural", k=5, *, breaks=None, pivot=None, palette="viridis", reverse=False, fmt="{:g}", missing_label="not counted", missing_color="#e2e8f0")` | `Classes` | colour classes for roads: `.labels`, `.breaks`, `.colors` and `.option(column)` (for `color_options`). `method` is `natural` (Fisher-Jenks), `quantile`, `equal` or `fixed`. A `pivot` is always a cut. `missing_label` and `missing_color` are for roads with no value ([parts](../guides/dashboard-parts.md#colour-classes)) |
| `natural_breaks(values, k)`, `ramp(palette, k)` | cuts, colours | the cuts of `classify`, and `k` colours along a palette |
| **Base maps, settings** ([Settings & palettes](settings.md)) | | |
| `BASEMAPS`, `Basemap`, `get_basemap`, `register_basemap` | | base maps ([below](#basemap)) |
| `set_api_key(key, provider=None)` / `get_api_key(provider=None)` | / `str` | base-map API keys |
| `StyleConfig` | | global styling knobs ([below](#styleconfig)) |
| `use_settings(*sources)` | | apply settings (path or dict) for the process; no argument drops them |
| `Overlay` | | an extra layer for the web backend ([below](#overlay)) |
| **Helpers** | | |
| `compute_levels(edges, band_col=None, order="priority", ...)` | edges + 4 columns | the level step in one call (`near_rules=False`: `True` also lifts parts that only come near; `head_m=5.0` decides once which parts of a stack cross; `method="solve"`): `casing_start`, `casing_level`, `casing_end`, `fill_level` ([design](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/level_input.md)) |
| `level_input(edges, id_col="edge_id", ...)` | `(roads, pairs)` | the solver's input from any edges: one row per road, one row per relation (`meet`, `stack` one row per crossing part of the upper road, `order`; `near` with `near_rules=True`); `head_m` / `heads` (a heads.csv table) decide which parts cross |
| `solve_levels(roads, pairs, edits=None, ...)` | roads + 4 columns | the solver, from the tables only (a stack: one row per part, `a_end` start / main / end); `edits` switch rows off or add them; `fixed` (`{road: (casing_start, casing_level, casing_end, fill_level)}`) holds those roads' numbers and solves the others (the editor's local re-solve); `max_positions` limits the number of positions |
| `level_area.make_area(edges, folder, db=None, ...)` / `level_area.solve_area(folder)` | `(roads, pairs)` / solved roads | an area folder (`roadstyle-levels make` / `solve`); with `db` every solve also writes into that DuckDB file |
| `render_edges(..., levels_db=file)` | – | reads `visualization.edge_levels` of a duckOSM file for these edges (some of the edges it was solved for; ids int64 or text); an error with level columns of your own |
| `save_area_levels(con, folder, *, schema="visualization")` / `load_area_levels(con, edges, *, schema="visualization", subset=False)` | – / edges + 8 columns | an area's result into `visualization.edge_levels` and back (the four numbers and each edge's ends); reading checks the edges |
| `save_levels(con, levels, *, schema="visualization")` / `load_levels(con, edges=None, *, schema="visualization", **expect)` / `restore_area_inputs(con, folder, *, schema="visualization")` | – / levels / – | the four level numbers of each edge into a duckOSM file and back; the area's input files from the file |
| `auto_ends(roads, pairs, zoom=18.0, ...)` / `casing_parts(roads, head_m=5.0, heads=None)` | tables | the end marks that the solver finds on its own; the casing pieces of each road |
| `is_directed(edges, driving_col="driving", cycling_col="cycling", highway_col="highway")` | bool column | the `directed_col` value: an edge open to cars or bikes that is not a path class |
| `export_inline(edges, **kw)` / `export_geojson(edges, out_dir, *, format="geojson", keep=None, **kw)` / `tile_geojson(src_dir, out, *, format="pmtiles", keep=None, base_url="")` | dict / dict / path | the style with its data inside; the style with its data as files; the tiles of those files |
| `normalize_highway(value)` | `(base, is_link)` | strip OSM `_link` |

A `WebMap` has `.html` (the page as a string), `.save(path)`, and shows inline in a notebook (Jupyter Notebook 7, JupyterLab): the
preview loads the bundled MapLibre version (5.24) from the jsDelivr CDN instead of inlining it, so it needs the network.

## `render_edges`

`render_edges(gdf, **kw)`: `gdf` is a GeoDataFrame (LineStrings + a `highway` column, any CRS) or
a `RoadEdges`. Every keyword is optional. **Backends** says which renderers read it; the others
ignore it.

### Look

| keyword | default | backends | what |
|---|---|---|---|
| `profile` | `None` | all | the name of a profile: every style value that is not a color (`default`, `highsat`, or `./profiles/<name>.yaml`); `None` = the one in force ([Profiles and palettes](settings.md#profiles-and-palettes)) |
| `backend` | `"web"` | | `"web"` (MapLibre, one offline file): the only backend ([Big networks](../guides/big-networks.md)) |
| `palette` | `"amber"` | all | `"amber"` (orange to green main roads, slate-grey streets), `"carto"` (soft OSM Carto tones), `"highsat"` (bright), `"mono"` or a registered palette |
| `basemap` | the `basemap` setting (`"ofm_positron"`) | all | a `BASEMAPS` key, a `Basemap`, a `{z}/{x}/{y}` URL or an xyzservices provider |
| `basemaps` | web: `ofm_liberty`, `ofm_positron`, `osm`, `esri_gray`, `esri_street`, `satellite`, `blank` (the seven base maps, each with its dark twin) | web | the base maps offered in the switcher: the base-map tool of the dashboard, and the base-map button of a map page |
| `basemap_switcher` | `True` | web | the base-map tool of the dashboard, or the base-map button of a map page, and its menu; `False` with a `basemaps=` list keeps the maps for `rsSetBasemap` |
| `zoom_readout` | `True` | web | the small "z 13.2" zoom number beside the scale bar (the dashboard shows the scale and the zoom number only when the person turns them on in the settings, or with `dashboard={"scale_box": True}`); `False` leaves it out |
| `api_key` | `None` | all | key for a keyed tile provider ([order](settings.md#base-maps-api-keys)) |
| `arrows` | `True` | web | one-way chevrons along each one-way edge |
| `labels` | `True` | web | curved street names from the `name` column |
| `legend` | `True` | web | a legend for data colouring (class styling has none). Web: a page key; the style always has the legend data (`roadstyle:color_options`) |
| `name` | `"roadstyle"` | web | the page title |
| `hover_color` / `select_color` | `"#b388ff"` / `"#7c4dff"` | web | highlight of the hovered / selected road |
| `minzoom` | `None` (the same for `render_dashboard`) | web | hides minor classes when zoomed out. `None` or `True`: the `minzoom` setting. A dict changes parts of it. `False`: all classes at all zooms. The box under the table has the keys of the dict. |
| `offset_frac` | `0.28` | web | two-way lane offset, fraction of the road's pixel width; `0` = no lane split |
| `width_frac` | `0.6` | web | each lane's width, fraction of the full road width |
| `offset_zoom` | `15` | web | zoom where the two directions start to fan apart |
| `settings` | `None` | all | a settings override for this call only: a dict, or the path of a JSON or YAML file; a file that cannot be read is an error ([levels](settings.md#settings-levels)) |

??? info "minzoom (dict)"
    The dict changes parts of the `minzoom` setting. The key `"*"` sets every class first: `{"*": 0, "service": 14}` shows every class at every zoom except the service roads. The key `"@private"` is the first zoom of the roads with private access (`access_col`), for any class.

### Filtering

| keyword | default | backends | what |
|---|---|---|---|
| `include` / `exclude` | `None` | all | keep only / drop these classes (str or list) |
| `match_links` | `True` | all | `primary` also matches `primary_link` |
| `filter_control` | `True` | web | no effect: the floating Roads box is gone. The `roads` tool of the dashboard is the road filter, and `rsSetClasses` filters from a script |
| `filter_col` | `None` | web | the column that `rsSetClasses` filters by, when it differs from `highway_col` |
| `find_control` | `False` | web | a "Search roads…" box in the top-left stack (the docked panel has its own); the JS `rsFind(text)` is always defined ([design](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/sensor_matching_requests.md)) |
| `overlay_control` | `True` | web | `False` hides the *Layers* box of the overlays on a map page, and the one switch of the style's base-map layers on a dashboard; `rsSetOverlay` still works. A page with a bar has no Layers box |
| `hillshade` | `False` | web | `True`: the *Hillshade* switch of the base-map box starts on (the person's saved choice in the browser wins). The shade is drawn under the roads from the DEM of `data/basemaps.json` `ontop.dem` (Terrain Tiles on AWS, no key) |
| `terrain` | `False` | web | `True`: the *3D terrain* switch of the base-map box starts on (the saved choice of the person wins). Use `pitch=` to tilt the camera: a flat camera shows the hillshade only. A tunnel is drawn on the hill above it and a bridge in the valley under it, because MapLibre has no height for a line |
| `terrain_exaggeration` | `None` | web | the height of the 3D terrain as a multiple of the DEM's: `2.0` doubles every hill, `0.5` halves it. `None`: `ontop.terrain.exaggeration` of `data/basemaps.json` (`1.0`). Read when the terrain switches on |
| `terrain_tunnels` | `"fade"` | web | what a tunnel does while the 3D terrain is on. `"fade"`: its fill, gap and dashes show at `ontop.terrain.tunnel_fade` of `data/basemaps.json` (`0.25`). `"hide"`: they do not show. `"show"`: no change. No effect with the terrain off |
| `buildings_opacity` | `None` | web | the opacity of the 3D buildings of a vector base map, from 0 to 1. `None`: `ontop.buildings.opacity` of `data/basemaps.json` (`1`, solid). The *Opacity* slider and `rsBuildingsOpacity(value)` change it. Another value is an error |
| `overlay_popup` | `True` | web | `False`: no overlay shows a click popup (it stays clickable and fires `rs:select`); one overlay: `Overlay(popup_window=False)` |
| `access_col` | `None` | web | a column with `private`, `bus`, `pedestrian`, `delivery` or nothing. A road with a value gets the access colour (`#c8c8c8`, `#9db8d9`, `#dddde8`, `#e8d2b0`) and a row in the `roads` tool. Use `rsSetAccess`, `rsGetAccess` and `RS_ACCESS`. The class row `pedestrian` goes when all its roads have an access kind |

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
| `color_options` | `None` | web | `{name: {styler kwargs}}`: a *Colour by* menu that recolours in the browser; the first entry shows on open |
| `color_active` | `0` | web | the option shown on open (index or name) |
| `template` | `None` | web | `"map"` (no panel; the default of `render_edges`) or `"dashboard"` (the default of `render_dashboard`). The dashboard sets the panel (empty), the toolbar and the window rules; its map has the defaults of `"map"`. The old `sidebar=` and the names `"classic"` and `"report"` are errors |
| `layout` | `None` | web | the dashboard's frame: `"overlay"` (default: the map fills the window, the panel floats, a toolbar) or `"dock"` (the panel is docked at the left and takes its own space, no toolbox). `template="dashboard"` only |
| `views` | `None` | web | `{name: {setting: value}}`: a *View* menu next to *Colour by*; each view sets several things at once, the first shows on open |

Each `color_options` value takes `color_by`, `colors`, `cmap`, `vmin`, `vmax`, `width_by`,
`palette`, `style`, `missing`; `{}` is the class style. See [Colour by your data](../guides/colour.md).

A `views` entry sets only what it names: `color` (a `color_options` name), `road_fill`, `bridges`, `tunnels`, `view3d`
(`True` / `False`), `overlays` (`{label: True / False}`), `classes` (a list of road classes), `basemap` (a key), `palette` (a palette
name: every color of the map, [Profiles and palettes](settings.md#profiles-and-palettes)). An unknown setting, or a name the page does not
have, is an error. Each palette that a view names is built once more into the page, so the page is somewhat larger.

A view sets only what it names, so name the same settings in every view when they must switch back. `palette` switches every color of the map: the road classes, and also the names, arrows, bridges, tunnels and the swatches of the `roads` tool. A color option with a palette (`{"palette": "carto"}`) recolors only the road fills. A page with the toolbox bar (the dashboard) hides the *View* menu: call `rsSetView(name)` from your own control there. `rsSetRoadFill(on)` sets the fill alone.

```python
rs.render_edges(edges, views={"Day": {"palette": "amber", "basemap": "ofm_positron"},
                              "Night": {"palette": "mono", "basemap": "ofm_dark"}})
```

### Popups & hover

| keyword | default | backends | what |
|---|---|---|---|
| `road_popup` | `True` | web | on click: `True` = `name`, `edge_id`, `edge_ref`, `highway`, `lanes`, `bridge`, `tunnel`; a list = those columns; `"all"`; `"panel"` = docked panel; `False` = none (`rs:select` still fires) |
| `popup_mode` | `None` (= `"popup"`) | web | `"panel"` docks the read-out in a side panel with a search box |
| `side_panel_html` | `None` | web | the HTML of your own full-height panel on the right, with the docked panel's » handle, « map button and `rsPanelShow(on)`; the open or closed state is kept per page; `--rs-side` follows it. An error with `popup_mode="panel"` |
| `host_panel_width` | `320` | web | the width of that panel, px |
| `road_tooltip` | `False` | web | on hover: `True` = every column, a list = those columns. Not on a touch-only device (a phone): a tap is a click |
| `hover_delay_ms` | `300` | web | a road or an overlay item lights up and shows its tooltip once the mouse rests this long on it (a passing mouse lights nothing); `0`: at once |
| `data_maxzoom` | `None` | web | the last zoom MapLibre cuts the GeoJSON sources into tiles at; above it, MapLibre enlarges those tiles and does not cut them again. Positions are as exact as the tile grid of that zoom. `None`: MapLibre's own |
| `data_tolerance` | `None` | web | how far MapLibre simplifies the road geometry when it cuts tiles in the browser. `None`: `0.05`, which keeps every vertex. A higher value (`1`) makes a sweep at zoom 12 about three times faster, and the picture is the same from zoom 14 |
| `tooltip` | `None` | web | hover columns. Web: alias of `road_tooltip`, `None` = no tooltip. Folium: `None` = all columns |

### Street View

| keyword | default | backends | what |
|---|---|---|---|
| `street_view` | `"window"` | web | `"window"`: a map button and a floating window that follows the clicked road. `"dock"` (dashboard): Street View beside the map, with a divider and no panel ([Docked](../guides/street-view.md#docked-beside-the-map)). `True`: a link in the popup. `False`: none. The page must be served over http(s) ([guide](../guides/street-view.md)) |
| `street_view_key` | env `GOOGLE_MAPS_KEY` | web | a Google Maps JavaScript API key for the window: its bar offers Linked (a panorama; the map marker walks with the viewer) and Classic (the embed). Written into the page; restrict it to your site's addresses ([Keys and tokens](../guides/google-key.md)) |
| `mapillary_token` | env `MAPILLARY_TOKEN` | web | a free Mapillary client token (mapillary.com/developer) for the Mapillary tab and its coverage layer. A token that the person saves in the settings wins. Panoramax needs no key. The page contains the token: limit it to your site |
| `google_3d` | on with a toolbar, else `False` | web | `True`: a Google 3D button and a floating window with Google's photorealistic 3D view; its camera and the map's move together, and a clicked road is drawn in it. Needs `street_view_key` (an error without it) ([guide](../guides/google-3d.md)) |
| `google_3d_layers` | `[]` | web | layers for the Google 3D window. Each is `{id, kind, source, match, scope, max, on, arrows, style}`; a wrong key or `kind` is an error. A layer draws the features of a GeoJSON source of the page ([guide](../guides/google-3d.md#your-own-layers)) |

### Camera & 3D

| keyword | default | backends | what |
|---|---|---|---|
| `pitch` / `bearing` | the `camera` setting (`0` / `0`) | web | starting tilt / rotation in degrees |
| `max_pitch` | the `camera` setting (`70`) | web | the most the map can tilt, in degrees. `60` keeps the view where MapLibre itself uses one tile zoom. Above 60 the page forces one tile zoom on the whole screen (a road has one width everywhere), and that loads 2 to 3.6 times as many tiles |
| `view_3d` | `False` | web | open tilted to `camera.pitch_3d`, with raised 3D bridge decks |

### Output & scale

| keyword | default | backends | what |
|---|---|---|---|
| `tiles` | `True` | web | `True`: the roads are embedded PMTiles (MLT, or MVT with `tile_format="mvt"`). `False`: the roads are GeoJSON, which MapLibre cuts in the browser. A page with a palette in a view needs `tiles=False` (an error says so). The box under the table has the measures. |
| `tile_format` | `"mlt"` | web | the format of the embedded tiles and of the tiles of `export_style`: `"mlt"` or `"mvt"` (for an app with MapLibre GL JS older than 5.12). No effect with `tiles=False` ([Make tiles and PMTiles](../rust/tiles.md#the-tile-format-mlt-or-mvt)) |
| `live_data` | `False` | web | writes the metadata `roadstyle:live` (the feature states `rs_c` and `rs_w`, the default ramp, the no-data colour; [contract](contract.md)) and the page option `live`, which `rs.setData` reads |
| `keep_let` | `False` | web | `export_style` and `export_inline` only: `True` keeps the `let` of the width table in the style (a smaller style). `False` writes each `let` as its value, because an app such as RustGIS cannot read `let`. A page and its tiles always keep the `let` |
| `compress` | `True` | web | gzip the inlined data; `False` = plain JSON |
| `tunnel_control` | `False` | web | on a map page with tunnels, shows a *Tunnels* box with the colour list (`tunnels.toward`), the strength slider (`tunnels.strength`), the casing palette and the dash ratio. A page with a bar hides it ([design](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/tunnel_look.md)) |

??? info "tiles and tile_format"
    With `tiles=False`, MapLibre cuts the GeoJSON in the browser and keeps every vertex. On 22,000 roads (Nacka, 173,000 pieces) that draws 2.4 to 2.6 times the triangles at zoom 11 to 13, and panning is slower. MLT is the default format for every path: it is about 60 % of the bytes of MVT after gzip, and the picture is the same.

Returns a `WebMap` (`.save()`).

### Column mapping

| keyword | default | backends | what |
|---|---|---|---|
| `highway_col` | `"highway"` | all | the road-class column (widths, casing, draw order) |
| `tunnel_col` / `bridge_col` | `"tunnel"` / `"bridge"` | all | tunnels draw under (faded, two-tone dashed casing), bridges on top |
| `layer_col` | `"layer"` | web | OSM `layer`; negative sinks an edge when there is no tunnel/bridge column |
| `casing_start_col` / `casing_end_col` / `head_m` | `None` / `None` / `5.0` | web | the casing numbers of the start head and the end head (the main number is `casing_level_col`). `head_m` is the length of each head in metres. The box under the table says how the casing is divided. |
| `head_start_m_col` / `head_end_m_col` | `None` | web | an edge's own head lengths in metres (`solve_levels`' `head_start_m` / `head_end_m`); null = `head_m`. A road shorter than its two heads is cut in their ratio |
| `road_fill` | `True` | web | `False`: draw the casing of each road but not its fill (the fill layers stay, invisible, for clicks); the items attached with `Overlay(edge_col=...)` are the fill |
| `edge_id_col` | `"edge_id"` | web | the column with the id of each edge, the ids that an overlay's `edge_col` refers to; the docked panel's search always reads it, whatever `road_popup` lists |
| `casing_level_col` / `fill_level_col` | `None` | web | two integer columns: the drawing position of the casing and of the fill of an edge (0 = ground). The position alone decides, a bridge too. Not given: `render_edges` calls `rs.compute_levels(edges)` ([guide](../guides/levels.md), [design](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/level_input.md)) |
| `cap_col` | `None` | web | a column of true / false: true draws the edge with square ends (butt caps) instead of round ones, for a road drawn in pieces that meet without a ring; `"square"` = flat but as far past the end as a round end (the drawn length kept); null / false = round ends |
| `cap_start_col` / `cap_end_col` | `None` | web | one end each, same values as `cap_col` (and `"round"`); null = `cap_col`'s. An edge whose two ends differ is drawn from its casing heads and two fill halves (position mode) |
| `width_m_col` | `None` | web | a column of widths in metres (a lane, a road with a `width` tag, a canal): from `width_m_zoom` on the line is drawn exactly that wide, its casing inside; null = the class width |
| `width_m_zoom` | `16` | web | the zoom from which `width_m_col` widths apply; below it, the class widths (so a narrow line doesn't vanish zoomed out) |
| `casing_m` | `0.15` | web | with `width_m_col`: the casing on each side, in metres, inside the width (two lines side by side show a `2 × casing_m` divider) |
| `casing_min_px` | `0` | web | a casing in metres is never thinner than this many pixels each side of its fill (0 = exact metres, a thin casing goes under a pixel) |
| `directed_col` | `None` | web | a column: true or null = the edge is a direction of travel of its own. False = undirected (for example a footway stored both ways). An edge and its reverse are two lanes only when neither is false; if not, they are one centred line. `rs.is_directed(edges)` makes the column |
| `driving_col` | `None` | web | a column: true / null = cars may drive the edge, false = they may not (duckOSM's `driving`). An edge gets a one-way arrow only if it is one-way (`oneway`, else no twin) and driving. Arrows only: the drawing (two directions or one line) is `directed_col`'s. `None` = every edge counts as driving |

??? info "levels and heads"
    With the level columns, the casing is divided into a start head, a main part and an end head. An edge at least `2 · head_m` long whose three casing numbers differ is drawn as three casing pieces, each at its own number. The fill stays one line ([design](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/levels_split_casing.md#9-the-renderer)). At each position the casings come first, then the fills.

??? info "directed_col"
    `rs.is_directed(edges)` marks an edge open to cars or bikes (`driving` or `cycling`) that is not a path class (`single_line_classes`). So a one-way street whose reverse is a bus lane or a bike lane is two halves, and its arrow is on the car edge.

### Overlays & boundary

| keyword | default | backends | what |
|---|---|---|---|
| `overlays` | `None` | web | a list of [`Overlay`](#overlay): zones, points, lines |
| `items` | `None` | web | the line items of a road (lanes, lane lines, marks): a GeoDataFrame or FeatureCollection. Each feature names its road in `edge_id_col` and has `width_m`; optional: `order`, `offset_m`, `color`, `dash`, `pick`, `minzoom`. A `pick` item is clicked as itself (`rs:select` `detail.item`); a click on the others goes to their road |
| `items_popup` | `None` | web | the fields a clicked `pick` item shows (`None`: all of its fields) |
| `boundary` | `None` | web | a dashed outline on top: shapely geometry, GeoDataFrame or GeoJSON. It is an input: the caller says where it comes from (a duckOSM `main.boundary`, a city limit, a drawn shape) |
| `boundary_dim` | `False` | web | `True`: shade the outside of `boundary` (the opacity is in the template's `boundary` options) |
| `dashboard` | `None` | web | a partial dashboard option, merged over the defaults of the template `dashboard`: `{"toolbar": {"position": "left"}, "panel": {"sections": [...]}}`. A wrong key or value is an error. Every key, default and meaning: [Dashboard options](#dashboard-options). `template="dashboard"` only |
| `page_script` | `None` | web | JavaScript text that the page runs, the last script of the body, before the page is ready: it sees `rs`. Put the code in `rs.ready(() => ...)`, which runs it when the panel's sections are there (and at once if they are) ([Live data](../guides/dashboard-manual/javascript.md#live-data-a-new-day)) |
| `page_style` | `None` | web | CSS text of the page, the last style of the body |
| `boundary_limit` | `False` | web | `True`: the camera stays near `boundary` (the center inside its bounds grown by `limit_pad`, and the lowest zoom `zoom_out` levels under the fit) |

## Pages

Web-only page builders. Each takes every `render_edges` keyword and returns a `WebMap`; they only
change the defaults below.

| function | page | changed defaults | own keywords |
|---|---|---|---|
| `render_dashboard` | the map, an empty panel to which the page adds parts (`dashboard={"panel": {"sections": [{"id": "q", "part": "query"}]}}`, [Dashboards](../guides/dashboards.md#the-panel-starts-empty)) and the standard toolbox | `template="dashboard"`; the map has the defaults of a map page; the panel is at the left, the toolbox at the right edge, no scale box | `layout="dock"`: the panel is docked at the left and there is no toolbox. The default `"overlay"` floats the panel over a full map ([Dashboard layout](../guides/dashboard-layout.md)) |
| `render_street_view` | map + Google Street View of the clicked road | `name="Roads and Street View"`, `road_popup=False`, `street_view=True` | see below |

| `render_street_view` keyword | default | what |
|---|---|---|
| `layout` | `"beside"` | `"beside"` = Street View right of the map, `"below"` = under it |
| `panel_width` | `42` | Street View's share of the window, 20-80 % (of the height when below) |
| `resizable` | `True` | a divider the viewer can drag; the choice is remembered in their browser |
| `street_view_key` | env `GOOGLE_MAPS_KEY` | a Google Maps JavaScript API key: the panel becomes a real panorama, the map marker walks and turns with the viewer, and it shows Google's own street imagery only. Written into the page; restrict it to your site's addresses |

## Dashboard options

`dashboard=` is a partial option of the template `dashboard`. The call merges it over the defaults of the template, field by field. Give only the keys that you change. A wrong key or value is an error, and so is `template` (use the keyword `template=`). Guides: [Dashboard layout](../guides/dashboard-layout.md) for the frame and the toolbox, [Dashboards](../guides/dashboards.md#the-panel-starts-empty) for the panel.

```python
rs.render_dashboard(edges, dashboard={
    "toolbar": {"position": "left"},
    "panel": {"side": "right", "look": "card", "width_px": 360},
})
```

The options are in groups: the frame (`layout`, `scale_box`), `panel`, `toolbar`, `legend`, `credits`, `windows`, `boundary` and `google_3d`. The defaults below are those of `layout="overlay"`. `layout="dock"` has no toolbar, and its `windows` default to `clamp` False and `recenter_map` True.

**Frame**

| key | default | meaning |
|---|---|---|
| `layout` | `"overlay"` | `"overlay"`: the map fills the window and the panel floats over it. `"dock"`: the panel takes its own space at the left and there is no toolbox. The page keyword `layout=` sets it |
| `scale_box` | `False` | `True` shows the scale and the zoom number at the start. The person can change it in the settings |

**`panel`** (`None` removes the panel: the page is the map and the toolbox)

| key | default | meaning |
|---|---|---|
| `side` | `"left"` | `"left"` or `"right"` |
| `width_px` | `400` | the width of the panel. Fit the content to the panel and do not widen the panel for it |
| `look` | `"card"` (`layout="overlay"`), `"frame"` (`layout="dock"`) | `"card"`: a floating card, see-through, over the map. `"frame"`: full height, with a translucent frame and solid cards. |
| `sections` | `[]` | the sections that the page adds to the empty panel, in order. A section is a mapping with the keys of the next table |

`panel.help` (none by default): `{"title", "intro", "terms", "note"}`, the "?" in the panel's title and the words of its help window ([A help window](../guides/dashboard-parts.md#a-help-window)).

A section (`panel.sections`; the errors are in [Dashboards](../guides/dashboards.md#the-errors)):

| key | default | meaning |
|---|---|---|
| `id` | required | the name of the section. It is not empty and not used twice |
| `part` | none | a part of roadstyle: `"query"`, `"road_card"` or `"chart"`. A section has one of `html`, `part`, `tabs` and `kpis` |
| `html` | none | the page's own HTML |
| `text` | none | the start text of the part `query` (none: an empty box) |
| `fields` | none | the columns that the part `road_card` shows (none: every column) |
| `chart` | none | the options of the part `chart`: the next table ([Charts](../guides/dashboard-parts.md#a-chart)) |
| `label` | none | the title of the section: a section with a `label` is a card, and a section without one is a block of the page's HTML with no box |
| `after`, `before` | none | the `id` of an earlier section: this section goes after it, or before it. Give one of them |
| `fold` | `False` | `True`: the card folds; its title is a button, and its row has a chevron. It needs a `label` |
| `note` | – | one line of state under the card's title (`rs.sections.note` changes it). It needs a `label`. A card that opens something (`open`, a function) is JavaScript only: [A card that opens something](../guides/dashboard-parts.md#a-card-that-opens-something) |
| `background` | `True` | `False`: the card has no colour behind it (the same padding and title row). It needs a `label` |
| `tabs` | none | in place of `html`: `[{"id", "label", "html"}, ...]`, a tab row and one pane for each tab ([Tabs](../guides/dashboard-parts.md#tabs)) |
| `kpis` | none | in place of `html`: `[{"title", "value", "sub", "color"}, ...]`, number tiles; `value` is a text or a number ([Number tiles](../guides/dashboard-parts.md#number-tiles)) |
| `help` | none | `{"title", "intro", "terms": [[term, meaning], ...], "note"}`: a "?" in the card's title row that opens the help window. It needs a `label` |

A chart card (`chart` of a section with `part: "chart"`; [Charts](../guides/dashboard-parts.md#a-chart)):

| key | default | meaning |
|---|---|---|
| `kind` | required | `"bar"`, `"line"`, `"histogram"`, `"scatter"` or `"pie"` |
| `x` | required | a column: the groups (bar, pie), the order (line), the numbers (histogram, scatter) |
| `y` | none | a number column, or a list of up to 3 (bar, line). None: the count of rows. Not for a histogram; necessary for a scatter |
| `agg` | `"sum"` | how the rows of one value of `x` join: `"sum"`, `"mean"`, `"min"`, `"max"` or `"count"` |
| `scale` | `1` | a factor for the values of `y` (`0.001`: metres to km). Not 0 |
| `data` | none | the page's own rows: a DataFrame, a GeoDataFrame (its geometry is not used), a list of dicts, or `{"columns": [{"name", "type"}], "rows": [[...]]}`. None: the map's roads. `x` and `y` are columns of `data` |
| `title` | none | the title of the chart (none: the card's `label` is the title) |
| `height` | `220` | the height of the chart in pixels, 80 or more |
| `follow` | `False` | the map's roads only: `True` draws the chart again for the roads that the map shows now |

The space of the cards is three CSS variables on `:root`: `--rs-card-gap` (12px, between two cards), `--rs-card-pad` (14px, inside a card) and `--rs-panel-bottom` (28px, under the last card). See [Cards: the panel standard](../guides/dashboard-parts.md#cards).

There is no `hide` key and no `phone` option. The page turns to its phone form by itself when the window is 700 px wide or less (a phone, or a narrow desktop window), with the bar at the top. The page data holds these fixed values as `phone.max_width_px` (700) and `phone.toolbar` (top). `dashboard=` cannot change them.

**`toolbar`** (`None`: no toolbox)

| key | default | meaning |
|---|---|---|
| `position` | `"right"` | `"right"`, `"left"`, `"top"` or `"bottom"` |
| `align` | `"middle"` | the place of the bar along its edge: `"start"` (the left corner of a bar at the top or the bottom, the top corner of a bar at the left or the right), `"middle"` or `"end"`. The Settings box has it as "Toolbar place" |
| `navigation` | `"box"` | `"box"`: one compass-needle button that opens a box with a zoom, a turn and a tilt slider. `"buttons"`: the buttons zoom in, zoom out, compass and 2D/3D |
| `settings` | `True` | shows the `settings` tool |
| `hold` | `False` | `True` keeps the bar hidden until your page calls `rs.tools.ready()`, or for 6 s |

**`legend`**

| key | default | meaning |
|---|---|---|
| `rows` | `[]` | rows that your page adds to the legend box, after the rows of the colour option. A row is `{color, label, shape}`. `shape` is `"square"` (default), `"circle"` or `"line"`. A wrong shape is an error |

**`credits`**

| key | default | meaning |
|---|---|---|
| `credits` | `[{"text": "© OpenStreetMap contributors", "href": "https://www.openstreetmap.org/copyright"}]` | the credits of your own data: `[{"text": ..., "href": ...}]`. They show before the credits of the base map. `[]` shows none of them. `href` is optional |

**`windows`**: the rules of the Street View and Google 3D windows

| key | default | meaning |
|---|---|---|
| `clamp` | `True` | keeps a window inside the free part of the screen |
| `recenter_map` | `False` | `True` moves the map when you drag a window |
| `restore_open` | `True` | opens again the windows that were open at the last visit |
| `remember` | `True` | keeps the size and the place of each window in the browser |

**`boundary`**: what the page does with the keyword `boundary=`

| key | default | meaning |
|---|---|---|
| `dim` | `False` | shades the outside of the boundary (the keyword `boundary_dim`) |
| `limit` | `False` | keeps the camera near the boundary (the keyword `boundary_limit`) |
| `dim_light`, `dim_dark` | `0.16`, `0.4` | the opacity of the shade in the light and in the dark theme |
| `limit_pad` | `2.0` | the center of the map stays inside the bounds of the boundary, grown by this share of their size |
| `zoom_out` | `3.0` | the lowest zoom is this many levels under the zoom at which the whole boundary fits the window |

A page with no `boundary=` has neither the shade nor the limit.

**`google_3d`**: the Google 3D window ([guide](../guides/google-3d.md))

| key | default | meaning |
|---|---|---|
| `fov_deg` | `None` | Google's vertical field of view. `None`: the range comes from the camera distance of the map |
| `follow` | `True` | the window starts with **Follow** on |
| `min_alt_m` | `80.0` | under this camera height, in meters, the window shows a note |
| `min_zoom_drawn` | `17.0` | over this map zoom, the drawn map shows the note |
| `mesh_altitude_m` | `1.5` | the height in meters over Google's mesh at which a line or a pin lies. At 0.5 m the bumps of the mesh cut a line into pieces |
| `selection_style` | see the next table | the line, the outline and the arrows of the selected road |
| `layers` | `[]` | layers from GeoJSON sources of the page. The keyword `google_3d_layers` sets them |

The keys of `selection_style`:

| key | default | meaning |
|---|---|---|
| `color`, `width` | `#22d3ee`, `8` | the line |
| `outline`, `outline_width` | `#0b1020`, `2` | the outline of the line |
| `arrow_color`, `arrow_width` | `#ffffff`, `5` | the arrows |
| `arrow_every` | `25` | meters between two arrows |
| `fill` | `rgba(34,211,238,0.35)` | the fill of a polygon |

A layer of `google_3d.layers` (an error: a missing `id`, `kind` or `source`, an `id` used twice, or the scope `selection` without `match`):

| key | default | meaning |
|---|---|---|
| `id`, `label` | required, none | the name of the layer, and its text in the **Show** menu |
| `kind` | required | `"line"`, `"ribbon"`, `"polygon"` or `"points"` |
| `source` | required | the id of a GeoJSON source of the page |
| `scope` | `"selection"` | `"selection"`: the features tied to the selected road. `"view"`: the features in the visible area |
| `match` | none | for the scope `selection`: the property that ties a feature to the road |
| `max` | `500` | for the scope `view`: the most features drawn |
| `on` | `True` | the layer starts shown |
| `arrows` | `False` | for the kind `line`: direction arrows along the line |
| `style` | `{}` | `color`, `width`, `outline`, `outline_width`, `dash` (`[m on, m off]`), `fill`, `width_m`, `width_prop` (the property that holds the ribbon width) and `radius` (for points). A key that does not fit the kind has no effect |

## Overlay

`rs.Overlay(data, ...)`: your own geometry, drawn with one flat style (web only). Defaults come from
the `overlays` setting. See [Add your own layers](../guides/overlays.md).

| field | default | what |
|---|---|---|
| `data` | required | GeoDataFrame, GeoSeries or GeoJSON (any CRS) |
| `kind` | auto | `"fill"`, `"line"`, `"circle"` or `"text"`; auto from the geometry (never `"text"`) |
| `placement` | `"over"` | `"under"` or `"over"` the roads |
| `color` | `"#6aa9ff"` | paint colour |
| `opacity` | fill `0.15`, circle `0.85`, line `0.9` | |
| `outline` | `color` | polygon outline colour; a circle's ring colour (default: the `circle_stroke` setting) |
| `radius` | `6` | circle radius, px |
| `width` | `2` | line / outline width, px; a circle's ring width (default 1) |
| `label` | `"Layer N"` | name in the *Layers* control, and the `layer` argument of the JS API |
| `popup` | `None` = all fields | fields on click; `[]` = not clickable |
| `popup_window` | `True` | `False`: clickable and selected (`rs:select` fires) but no popup (and no read-out in panel mode) |
| `tooltip` | `None` | fields on hover |
| `visible` | `True` | shown on open |
| `edge_col` | `None` | the property with the id of the feature's edge: the overlay is attached to edges, drawn at its edge's fill number (the guide: [Overlays](../guides/overlays.md#overlays-attached-to-edges)) |
| `order_col` | `None` | with `edge_col`: the property with the feature's order (whole number, lower first; null = 0) |
| `select` | `"road"` | with `edge_col`: a hover or click picks the feature's road (`"road"`) or the feature itself (`"item"`: its own highlight and popup, `rs:select` with `item` and the road); anything else is an error |
| `color_col` | `None` | the property with a colour per feature (null: `color`) |
| `width_m` | `None` | a line's width in metres, exact from `min_zoom` on (replaces `width`) |
| `dash` | `None` | a line's dash pattern in line widths, `[3, 3]` |
| `min_zoom` / `max_zoom` | `None` | the zooms in which the overlay is drawn |
| `style` | `None` | the name of a style in the setting `config.overlays.styles` (roadstyle has none). An argument given on the overlay wins over the style |
| `width_m_col` / `offset_m_col` / `dash_col` | `None` | with `edge_col` and line features: the property with each item's width in metres (else `width_m`), its line offset in metres (+ = right of the direction; null = 0) and its dash pattern in line widths (`[3, 3]` or `"3,3"`; null = `dash`) |
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
| `bg`, `preview`, `subdomains` | `"#444"`, three greys, `"abc"` | switcher thumbnail, tile subdomains |
| `style_url`, `group`, `title`, `dark`, `swatch`, `building_3d` | `None`, `""`, `""`, `None`, `""`, `""` | the fields of the base-map box (`data/basemaps.json`): a vector style URL, the group and title of its row, the key of its dark twin, its swatch, the colour of the 3D buildings of a dark vector style |
| `maxzoom` | `19` | the provider's last zoom level with real tiles; zoomed in further, the map scales that level up instead of showing missing tiles. Built-ins: Esri grey maps 16, the rest 19; xyzservices providers bring their own `max_zoom` |

## StyleConfig

The values the stylers read. Every field comes from the [profile and palette](settings.md#profiles-and-palettes). The field names below are the `config` keys; the last column of a row names the profile or palette key where it is stored. Change a value in a profile or palette, not in code.

| field | default | what |
|---|---|---|
| `fill_opacity` / `casing_opacity` | `0.9` / `0.75` | line opacities |
| `casing_extra` | `2.0` | reserved (palettes set casing widths) |
| `link_scale` | `0.6` | `*_link` width relative to the parent (theme `roads.links.width`) |
| `tunnel_opacity_scale` | `0.45` | tunnel fade |
| `tunnel_casing_dash` | `[1, 1]` | profile `tunnels.casing_dash`: the tunnel casing's dash and gap, in line widths; a tunnel's casing is its dash layer alone |
| `tunnel_strength` | `60` | profile `tunnels.strength` (0-100): everything on a tunnel (fill, names, arrows, attached items) moves toward the `tunnels.toward` colour. The Tunnels box has the steps 0, 25, 50, 55, 60, 65, 70, 75, 100 (`tunnels.steps`) |
| `tunnel_toward` / `tunnel_towards` | `Sand` / eight | palette `tunnels.toward` and `tunnels.towards`: the colour a tunnel moves toward. Use a name from `towards` (Slate, Dark, Light, Graphite, Navy, Stone, Sand, Teal) or any `#rrggbb`. A bad name or colour is an error that names the choices |
| `tunnel_palette` / `tunnel_palettes` | `Graphite + silver` / seven | palette `tunnels.palette` and `tunnels.palettes`: the tunnel casing. `One colour` is slate dashes with empty gaps. The other names are `[dash, gap]` pairs (`Slate + ice`, `Blue + cyan`, `Warm + sand`, `Graphite + silver`, `Indigo + lavender`, `Teal + mint`). A bad name is an error |
| `tunnel_fill_dash` / `tunnel_fill_dash_color` | `[]` (none; e.g. `[1.2, 1.2]`) / `rgba(255,255,255,0.55)` | light dashes along a tunnel's fill, over any road colour (`[]` = none); a dashed class (steps, a dashed path) keeps only its own dashes |
| `single_line_classes` | footway, path, steps, pedestrian, cycleway, track, bridleway, corridor, platform | a two-way pair of these classes is drawn as one line at full width, not as two lanes. Both edges keep their data, and a click shows both directions. `[]`: every pair is lanes |
| `twin_end_caps` | `true` | a two-way road ends like one road: one road-wide round cap under its two lanes at each end, where both lanes have the same colour (`false` = each lane's own round end) |
| `twin_casing` | `"one"` | a two-way road that is two directed edges. `"one"`: one casing around both directions, at the full width of the road. `"each"`: each direction has its own casing, half the width, shifted. The box under the table has the details of `"one"`. |
| `bridge_casing_m` / `bridge_casing_px` | `0.25` / `1.0` | with metre widths (`width_m_col`): the casing of a bridge deck is at least `bridge_casing_m` metres wide on each side, and never thinner than `bridge_casing_px` pixels on each side. The bridge look then shows on lines with no casing |
| `bridge_casing_extra` / `bridge_casing_color` | `1.5` / `"#64748b"` (slate) | profile `bridges.casing_extra` (px wider) / palette `bridges.casing_color` |
| `bridge_shadow` / `bridge_shadow_color` / `bridge_shadow_blur` / `bridge_shadow_offset` / `bridge_shadow_trim_m` | `true` / `rgba(0,0,0,0.25)` / `4` / `[2, 2]` / `3` | profile `bridges.shadow.show`, `blur`, `offset`, `trim_m`; palette `bridges.shadow.color`. A soft shadow under a bridge. Blur is in px; offset is in px right and down; no shadow over the last `trim_m` metres where the bridge comes down |
| `minor_no_casing` | cycleway, footway, living_street, path, pedestrian, service, track | classes drawn without casing |
| `casing.drop_below_px` | `1.0` (`0` = always a casing) | a casing piece is not drawn at a zoom where the whole casing line is narrower than this many px (a bridge keeps it). The tiles leave out these pieces. Nothing is dropped from a road in metres when `casing_min_px` is at least this value |
| `minzoom` | motorway 4 … residential 13 … footway 15 | class → hidden below this zoom (unless `minzoom=False`); the tiles leave out a hidden class |
| `basemap` | `"ofm_positron"` | the default base map |
| `labels` | `color #5b5b5b`, no halo | street-name paint; `size`: `[[zoom, px], ...]`, the names' size per zoom for every class (roads in metres) instead of following each class's width |
| `arrows` | `color #5b5b5b`, `opacity 0.7` | one-way chevron paint |
| `camera` | `pitch 0`, `bearing 0`, `pitch_3d 55`, `max_pitch 70` | starting camera and 3D tilt |
| `bridge_decks` | `base_m 5`, `thickness_m 1`, `ramp_m 40`, `step_m 2.5`, `match_zoom 18`, `opacity 0.7`, `width_scale 0.6`, `flat_below 16`, `casing_px 2` | 3D bridge decks |
| `overlays` | `color #6aa9ff`, `radius 6`, `width 2`, per-kind opacities, `circle_stroke #ffffff` | `Overlay` defaults |
| `annotations` | `slot_m 100` | label / arrow spacing along a road, metres |
| `tiles` | `minzoom 6`, `maxzoom 16`, `extent 4096`, `buffer_px 80` | the `tiles=True` tileset. The map scales the last zoom's tiles up. The engine gives each zoom the buffer of its widest stroke; `buffer_px` is the buffer of a zoom where a width cannot be bounded |
| `api_key` / `api_keys` | `None` / `{}` | default key / per-provider keys |

??? info "twin_casing-one"
    With `"one"`, the casing is drawn once from the casing pieces of the first edge (numbers, heads, caps). The two edges must agree when one is reversed; if not, a warning names the pair. Each direction keeps its own fill. The end caps are the casing's own. A dead end of a pair is square for the casing and both fills, unless a cap column gives a cap. The bridge shadow and the tunnel dashes follow the casing.

**See also:** [JavaScript API](javascript.md) · [Settings & palettes](settings.md) · [Command line](cli.md)
