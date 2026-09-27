---
name: roadstyle
description: Render road networks (a GeoDataFrame of edges with a `highway` column, e.g. from OSM or duckOSM) into styled, interactive, offline HTML maps with the roadstyle Python library, and script the saved map from JavaScript (rsQuery, rsColor, rsSelect, rs:select). Use when drawing roads or per-edge data (traffic flow, speed, clusters, routes) on a map, building a map dashboard or report page, or embedding a roadstyle map in a host page.
---

# roadstyle

Turns a GeoDataFrame of road edges into one self-contained HTML map (MapLibre, data inlined,
works offline) with real road cartography and a `window.rs*` JavaScript API.
Docs: https://khoshkhah.github.io/roadstyle/ (every keyword: `/parameters/`, JS API: `/web-backend/`).

## Install

`pip install roadstyle`; extras as needed: `numeric` (`cmap` ramps), `tiles` (`tiles=True`),
`duckdb`, `lonboard`, `studio`, or `all`. Check the installed version with
`python -c "import roadstyle; print(roadstyle.__version__)"` before relying on a recent keyword.

## Data contract

- Required: LineString `geometry` (any CRS, reprojected for you) and `highway` (OSM class).
- Optional columns switch features on: `name` (labels, popup title), `oneway` (arrows),
  `bridge` / `tunnel` / `layer` (grade separation), `edge_id` (kept exact past 2**53).
- Every other column shows in the popup and is queryable from JavaScript, so join your data
  onto the edges as columns before rendering.
- An edge is DIRECTED: its geometry runs the way traffic flows; a two-way road is two edges with
  reversed geometry, drawn side by side. Don't dissolve or dedupe the twins.
- Input may also be a file path, a GeoJSON dict, a pyarrow Table, or
  `rs.from_duckdb(con, "SELECT ..., ST_AsWKB(geom) AS geom FROM edges", geometry="geom", crs=4326)`.

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
- Other useful keywords: `include=[...]` / `exclude=[...]` (road classes), `view_3d=True`,
  `tiles=True` (above ~50k edges), `boundary=geojson` (dashed outline),
  `overlays=[rs.Overlay(gdf, placement="under"|"over", label=..., popup=[...])]`,
  `road_popup="panel"` (docked read-out instead of a popup), `arrows=`, `labels=`.
- Ready-made pages: `rs.render_dashboard(edges, ...)` (query sidebar) and
  `rs.render_report(edges, ...)` (stats sidebar) take the same keywords.
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
the page, beside the map: `examples/street_view_side_by_side.py` (Google blocks the
`detail.streetView` URL in iframes; the example converts it to a `google.com/maps/embed?pb=` one). Add your own panel by
inserting HTML before `</body>` in `m.html`.

## Traps (each one cost a real bug)

- **Ids past 2**53.** `rsSelect` / `rsColor` / `rsFocus` take roadstyle's *feature ids*, never
  your `edge_id`. Get them with `rsQuery(p => String(p.edge_id) === "8121729169906061189")`, or
  add a small integer column (e.g. `pidx = 0..n-1`) and query on that. In Python, a column mixing
  big ints and `None` becomes float64 and silently rounds the ids: use `dtype="Int64"`.
- **A host side panel covers the map controls.** roadstyle puts the base-map button and menu on
  `<body>`, positioned against the viewport. With a fixed side panel, inset the map and move them:
  `#map{right:400px!important} .bm-icon{right:410px} .bm-menu{right:410px}`.
- **Highlight by recolouring, not by drawing.** Use `rsColor` or a `color_options` entry. Extra
  lines drawn over the roads double them and hide the road's own styling.
- **A selection in the base colour shows nothing.** Pick a highlight colour no `color_options`
  entry already uses.
- **CARTO base maps are watermarked without a key** (`voyager`, `positron`, `dark_matter`). Use
  `osm` or `blank`, or set a free key: `rs.set_api_key("…", provider="carto")` / `CARTO_API_KEY`.
- **folium / lonboard backends** support only part of this: the JS API, `color_options`, 3D and
  overlays are web-backend (the default) only.
