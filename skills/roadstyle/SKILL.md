---
name: roadstyle
description: Render road networks (a GeoDataFrame of edges with a `highway` column, e.g. from OSM or duckOSM) into styled, interactive, offline HTML maps with the roadstyle Python library, and script the saved map from JavaScript (rsQuery, rsColor, rsSelect, rs:select). Use when drawing roads or per-edge data (traffic flow, speed, clusters, routes) on a map, building a map dashboard or report page, or embedding a roadstyle map in a host page.
---

# roadstyle

Turns a GeoDataFrame of road edges into one self-contained HTML map (MapLibre, data inlined,
works offline) with real road cartography and a `window.rs*` JavaScript API.
Docs: https://khoshkhah.github.io/roadstyle/ (every keyword: `/reference/parameters/`, JS API: `/reference/javascript/`, Street View: `/guides/street-view/`).

## Install

`pip install roadstyle`; extras as needed: `numeric` (`cmap` ramps), `tiles` (`tiles=True`), 
`duckdb`, `lonboard`, `studio`, or `all`. Check the installed version with
`python -c "import roadstyle; print(roadstyle.__version__)"` before relying on a recent keyword.

## Data contract

- Required: LineString `geometry` (any CRS, reprojected for you) and `highway` (OSM class).
- Optional columns switch features on: `name` (labels, popup title), `oneway` (arrows),
  `bridge` / `tunnel` / `layer` (grade separation), `edge_id` (kept exact past 2**53).
- Real widths: `width_m_col="width_m"` draws each line exactly that many metres wide from
  `width_m_zoom` (16) on, casing `casing_m` (0.15) inside it; null = the class width.
- Draw order: every edge is drawn by two positions (casing, fill), computed for you by
  `compute_levels(edges)` (the level step; `render_edges` takes no band or order). `compute_levels(edges,
  band_col="band")` (integers) sets the band of an edge (a sidewalk -1, a crossing 1). For a big network compute once:
  `rs.save_levels(con, rs.compute_levels(...))`, and draw with `casing_level_col=` / `fill_level_col=`.
  To fix places by hand: `roadstyle-levels make SOURCE AREA_DIR` -> `roadstyle-levels solve AREA_DIR` -> `roadstyle-levels edit AREA_DIR` (a local
  editor writing `edits.csv` / `heads.csv` / `caps.csv`); draw its `levels.csv` with `casing_start_col` / `casing_level_col` /
  `casing_end_col` / `fill_level_col` and the ends with `head_start_m_col` / `head_end_m_col` / `cap_start_col` / `cap_end_col`.
- Every other column shows in the popup and is queryable from JavaScript, so join your data
  onto the edges as columns before rendering.
- An edge is DIRECTED: its geometry runs the way traffic flows; a two-way road is two edges with
  reversed geometry, drawn side by side (a two-way footway, path, steps, cycleway ... is ONE full-width line, setting
  `single_line_classes`; its click shows both directions). Don't dissolve or dedupe the twins.
- Input may also be a file path, a GeoJSON dict, a pyarrow Table, or
  `rs.from_duckdb(con, "SELECT ..., ST_AsWKB(geom) AS geom FROM edges", geometry="geom", crs=4326)`.
- **osmnx edges go in as they are** (0.9+): `rs.render_edges(ox.graph_to_gdfs(G, nodes=False))`.
  Keep the graph directed. Build it with `simplify=False`, then
  `ox.simplify_graph(G, edge_attrs_differ=["bridge", "tunnel"])`: default simplification merges a
  tunnel with the bridge next to it, and the whole tunnel is then drawn as a bridge (roadstyle warns).

## The one call

```python
import roadstyle as rs

m = rs.render_edges(
    edges,
    palette="mono",                       # neutral roads, so the data colour reads
    color_options={                       # one entry per colouring; a dropdown switches them,
        "Flow":  {"color_by": "flow", "cmap": "turbo"},          # the first one shows on open
        "Level": {"color_by": "level", "colors": {"low": "#2a9d8f", "high": "#e63946"}},
        "Road class": {},
    },
    basemap="positron",                   # positron | voyager | dark_matter | osm | satellite | blank
    tooltip=["name", "flow"],             # hover fields (off by default)
)
m.save("map.html")                        # m.html is the page as a string
```

- One colouring only: `color_by="flow", cmap="viridis"` (numeric, needs `numeric` extra) or
  `color_by="level", colors={...}` (categorical). `width_by=(1, 6)` scales width by the value.
- Per-edge colours you computed: `color_table={edge_id: "#hex"}` (dict / Series / DataFrame).
- Several things switched at once (colour, road fill, overlays, classes, base map, 3D): `views={"Flow": {"color": "Flow",
  "overlays": {"lanes": False}}, ...}`, a *View* menu next to *Colour by*; `rsSetView(name)` from a host page.
- Other useful keywords: `include=[...]` / `exclude=[...]` (road classes), `view_3d=True`,
  `tiles=True` (above ~50k edges), `boundary=geojson` (dashed outline),
  `overlays=[rs.Overlay(gdf, placement="under"|"over", label=..., popup=[...])]`, attached to edges: `rs.Overlay(gdf, edge_col="edge_id", order_col="order")` (drawn at its edge's fill number, by order; a click selects its road, or with `select="item"` the item itself: `rs:select` `detail.item` plus the road), look from a library's theme: `rs.Overlay(gdf, style="dashed")` with `settings={"config": {"overlays": {"styles": {...}}}}` (`width_m`, `dash`, `min_zoom`, kind `text`), `render_edges(road_fill=False)` (the road's casing without its fill),
  `road_popup="panel"` (docked read-out instead of a popup), `arrows=`, `labels=`, `simple=` (default `True`: one road layer, fast on a big page;
  names and arrows above all roads, no twin end caps; `simple=False` is the full look; both work with `tiles=True`).
- Look: `palette="amber"` (the default), `"carto"`, `"highsat"`, `"mono"`. A street name shows where it fits inside its road
  (main roads from zoom 15-16, side streets from 17); one-way arrows on main roads from zoom 15, side streets from 17: check
  with `rs.snapshot(m, "x.png", center=(lon, lat), zoom=17)`. Bridges: slate outline and a shadow; tunnels fade and are dashed. `settings={"config": {"tunnel_toward": "Dark"}}` (a name in `tunnel_towards`, or a `#rrggbb`) picks the colour they fade toward (default Sand; Dark or Light matching the base map keeps each class hue).
- Ready-made pages: `rs.render_dashboard(edges, ...)` (query sidebar) and
  `rs.render_report(edges, ...)` (stats sidebar) and `rs.render_street_view(edges, ...)` (Google
  Street View beside the map, or under it with `layout="below"`, following the clicked road;
  `panel_width=42`, `resizable=True`)
  take the same keywords. CLI: `roadstyle edges.gpkg --page street-view`. Every map has a Street
  View button by default (`street_view="window"`): a floating, draggable, resizable window that
  follows the clicked road (`rsSetStreetView(on)`), a map marker (dot + cone) where it stands,
  and ◀ ▶ buttons stepping 15 m along the edge (`rsStreetViewStep(m)`, event
  `rs:streetviewmove`); `rsGetStreetViewSpot()` / event `rs:streetviewspot` read the spot back
  (edge `id`, metres `m` along it, `lng`/`lat`, `heading`, `source`: `"panorama"` = current, only
  with `street_view_key=`; `"map"` = the clicked or stepped spot); `street_view=True` = a plain popup link, `False` = none. Street View loads only
  when the page is served (http/https), not opened from disk: `python -m http.server`.
- Colours, widths, casing and camera defaults are settings, not keywords:
  `rs.render_edges(..., settings={"config": {"labels": {"color": "#888"}}})`.
- Unsure of a keyword? `help(rs.render_edges)` or the parameters page. Don't guess: an unknown
  or misspelt keyword is silently ignored, not an error.

## Check the result

Look at the map before reporting it done. With `pip install playwright && playwright install chromium`:

```python
rs.snapshot(m, "map.png", zoom=15)        # headless screenshot; then view map.png
```

## JavaScript API (in the saved page)

| call | does |
|---|---|
| `rsQuery(p => bool)` | features whose properties match -> **roadstyle feature ids** |
| `rsColor(ids, "#hex")` / `rsColor([[idsA, c1], [idsB, c2]])` / `rsColor(null)` | paint sets over the base colours / reset |
| `rsHighlight(ids)` | selection glow (`[]` clears) |
| `rsFocus(ids)` | fit the camera |
| `rsSelect(id)` / `rsDeselect()` | select like a click (glow + popup) |
| `rsFilter(ids)` / `rsFilter(null)` | show only these / all |
| `rsGetProps(ids)` | the rows behind the ids |
| `rsSetBasemap`, `rsSetClasses`, `rsSetColorField`, `rsSetOverlay`, `rsSetView3D` | drive the built-in controls |

Events on `document`: `rs:select` (`e.detail.properties`, and `e.detail.streetView`, a Google
Street View URL facing the edge's direction, or null; an overlay click sets `e.detail.overlay`,
a road click doesn't - test that, not `e.detail.layer`, which differs between click and `rsSelect`), `rs:deselect`, `rs:colorchange`,
`rs:filterchange`, `rs:basemapchange`. `window.map` is the MapLibre map. Street View *inside*
a custom page: Google blocks the `detail.streetView` URL in iframes; convert it to a
`google.com/maps/embed?pb=` one as `rs.sidebar_html("street_view")` does. Add your own panel by
inserting HTML before `</body>` in `m.html`.

## Traps (each one cost a real bug)

- **Ids past 2**53.** `rsSelect` / `rsColor` / `rsFocus` take roadstyle's *feature ids*, never
  your `edge_id`. Get them with `rsQuery(p => String(p.edge_id) === "8121729169906061189")`, or
  add a small integer column (e.g. `pidx = 0..n-1`) and query on that. In Python, a column mixing
  big ints and `None` becomes float64 and silently rounds the ids: use `dtype="Int64"`.
- **A host side panel covers the map.** Inset it: `#map{right:400px!important}
  body{--rs-side:400px}`. Every map control - zoom, 2D/3D, Street View and, since 0.8.0, the
  base-map button - lives in the map's own top-right column and moves with it; `--rs-side` shifts
  the rest (overlay toggle, Street View window). No `.bm-icon`/`.bm-menu` rules are needed any more.
- **Highlight by recolouring, not by drawing.** Use `rsColor` or a `color_options` entry. Extra
  lines drawn over the roads double them and hide the road's own styling.
- **A selection in the base colour shows nothing.** Pick a highlight colour no `color_options`
  entry already uses.
- **CARTO base maps are watermarked without a key** (`voyager`, `positron`, `dark_matter`). Use
  `osm` or `blank`, or set a free key: `rs.set_api_key("…", provider="carto")` / `CARTO_API_KEY`.
- **folium / lonboard backends** support only part of this: the JS API, `color_options`, 3D and
  overlays are web-backend (the default) only.
