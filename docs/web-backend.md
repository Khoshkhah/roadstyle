# MapLibre web backend (`backend="web"`)

The `web` backend renders a **self-contained, interactive MapLibre (vector) map** — the same
"geometry sandwich" cartography as the folium/lonboard backends, but drawn with MapLibre's native
zoom expressions so it matches the look of *openstreetmap-carto*. It is the **default backend**, so
you get it without passing `backend=`.

```python
import roadstyle as rs

edges = gpd.read_file("edges.gpkg")            # needs a `highway` column (any CRS)
rs.render_edges(edges, theme="dark").save("roads.html")            # web is the default
rs.render_edges(edges, backend="web", theme="dark").save("r.html") # explicit, same thing
```

`render_edges(..., backend="web")` returns a **`WebMap`** with `.save(path)` (and inline display
in a notebook). The saved file is **one HTML document with MapLibre and the road data bundled
inside it** — it opens with **no web server and no internet** (see [Offline](#offline-self-contained)).

From the command line this backend is `-f web` (the default): `roadstyle edges.gpkg -o map.html`.

> **Not the same as the roadstyle.js page.** `rs.save(...)` / the CLI's `-f rsjs` write the
> *roadstyle.js spec page* (a `__rs_*`-baked page for embedding — see
> [Frontend integration](frontend.md)). This page is about the **render backend**
> `render_edges(backend="web")` / `-f web`, a finished MapLibre map, not a spec.

## What it does that folium/lonboard don't

| Feature | What you get |
|---|---|
| **Per-zoom widths** | Roads widen smoothly as you zoom in (the osm-carto width-by-zoom table), instead of a fixed pixel weight. Fixes the "fixed-pixel roads blob when zoomed out" limitation of the other backends. |
| **Two-way directional lanes** | A two-way street's two directed edges fan into **parallel lanes** via a pixel-proportional `line-offset`, so you can see both directions. One-way edges stay centred. |
| **Direction arrows** | One-way edges get chevrons placed along the line (native `symbol-placement: line`). |
| **Street-name labels** | Names are placed along the road (curved), from the `name` column. |
| **Hover / select** | Hovering highlights the road under the cursor; clicking selects it and shows its attributes; clicking the background deselects (restoring the original colour). Driven by MapLibre `feature-state` — a GPU recolour, no re-layout. |
| **Base-layer switcher** | An in-map dropdown to switch the background (dark / light / voyager / satellite / OSM). |
| **Road z-order** | Higher-class roads draw over lower ones at junctions (a motorway over a residential), with `_link` ramps tucked just under their through road. |
| **Tunnel / bridge grade separation** | Tunnels draw *underneath* (dashed + faded), bridges draw *on top* (heavier, square-capped casing) — see below. |

## Grade separation (tunnels & bridges)

If your data carries `tunnel`, `bridge`, and/or `layer` columns, the backend orders
grade-separated roads by elevation so a tunnel passing *under* a street no longer looks connected
to it, and a bridge reads as a deck spanning what's below.

One baked integer per edge, `lvl`, drives everything:

- `bridge` truthy → `+1`, `tunnel` truthy → `-1`, else the sign of the `layer` tag, else `0`.
- `lvl` feeds the **draw order** (`lvl*1000 + class_rank` in `line-sort-key`, so every tunnel is
  below every surface road and every bridge above), the **layer an edge lands in**, and its
  **per-grade style**:
  - **tunnels** — a *dashed*, butt-capped casing over a *faded* fill (reads as "underground");
  - **bridges** — a *heavier* (1.25×), butt-capped casing (reads as a deck).

Columns absent ⇒ every edge is treated as ground level (no change). Override the column names with
`tunnel_col` / `bridge_col` / `layer_col`.

```python
# DuckDB driving graph that carries grade tags
edges = rs.from_duckdb(
    con,
    "SELECT highway, name, oneway, layer, bridge, tunnel, ST_AsWKB(geometry) AS geom "
    "FROM driving.edges",
    geometry="geom", crs=4326,
)
rs.render_edges(edges, backend="web", theme="dark").save("city.html")
```

## Parameters

All the shared `render_edges` arguments apply (`palette`, `theme`, `include`/`exclude`,
`color_by`/`cmap`/`width_by`, `style`, `highway_col`, `basemap`, `basemaps`, `name`). The
backend adds:

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `arrows` | bool | `True` | Show one-way direction chevrons along each one-way edge. |
| `labels` | bool | `True` | Show curved street-name labels (from the `name` column). |
| `filter_control` | bool | `True` | Show the collapsible **road-class filter panel** (a checkbox per class present; unchecking hides that class across every road layer). |
| `basemap_switcher` | bool | `True` | Show the in-map **base-layer dropdown** (its options come from `basemap` / `basemaps`). |
| `offset_frac` | float | `0.28` | Two-way lane offset as a fraction of the road's **pixel** width (pixel-proportional ⇒ constant overlap at every zoom). `0` = no lane split. |
| `width_frac` | float | `0.6` | Each two-way lane's width as a fraction of the full road width once the directions have fanned apart (a little over `0.5` so the two lanes overlap rather than leave a centre gap). |
| `offset_zoom` | int | `15` | Zoom at which lanes start fanning apart / splitting (ramped in over ~2 zoom levels). Below this the two directions stay coincident. |
| `tunnel_col` | str | `"tunnel"` | Column marking tunnels (used for `lvl`). |
| `bridge_col` | str | `"bridge"` | Column marking bridges. |
| `layer_col` | str | `"layer"` | OSM `layer` tag column (signed elevation when tunnel/bridge are absent). |

From the CLI these map to `--no-arrows` / `--no-labels` / `--no-filter` / `--no-basemap-switcher`.

## Offline / self-contained

The saved HTML bundles MapLibre's JS+CSS **inline** and inlines the road GeoJSON, so:

- it **opens straight from disk** (`file://`) with **no web server** and **no internet** — the
  road network always renders;
- the only online bits are the **base-map raster tiles** and **label glyphs**; offline those simply
  don't draw (blank background, no labels), but the roads still do.

This is what makes the output a true single-file deliverable. (The folium/lonboard backends and the
[roadstyle.js spec page](frontend.md) have their own delivery models.)

## When to use which backend

- **`web`** — a finished, interactive, **zoom-correct** road map you can ship as one file. The best
  default when you want the osm-carto look, two-way lanes, grade separation, and an offline page.
- **`folium`** — quick portable Leaflet HTML; fixed-pixel widths; rich folium ecosystem.
- **`lonboard`** — GPU/WebGL for very large edge sets.
- **`to_spec` / `save` / `-f rsjs`** — when the **browser** (your own Leaflet/MapLibre/deck.gl page)
  should draw the data and you just want roadstyle's styling baked into JSON. See
  [Frontend integration](frontend.md).
