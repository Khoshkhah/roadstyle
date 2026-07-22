# MapLibre web backend (`backend="web"`)

The `web` backend renders a **self-contained, interactive MapLibre (vector) map** — the same
"geometry sandwich" cartography as the folium/lonboard backends, but drawn with MapLibre's native
zoom expressions so it matches the look of *openstreetmap-carto*. It is the **default backend**, so
you get it without passing `backend=`.

```python
import roadstyle as rs

edges = gpd.read_file("edges.gpkg")            # needs a `highway` column (any CRS)
rs.render_edges(edges, basemap="dark_matter").save("roads.html")            # web is the default
rs.render_edges(edges, backend="web", basemap="dark_matter").save("r.html") # explicit, same thing
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
| **Base-layer switcher** | An in-map dropdown to switch the background (dark / light / voyager / satellite / OSM / a tile-less `blank` canvas). |
| **Road z-order** | Higher-class roads draw over lower ones at junctions (a motorway over a residential), with `_link` ramps tucked just under their through road. |
| **Tunnel / bridge grade separation** | Tunnels draw *underneath* (dashed + faded), bridges draw *on top* (heavier, square-capped casing) — see below. |
| **Dynamic recolouring** | Bake several "colour by" options with `color_options=` and switch between them client-side from a **Colour by** dropdown — no re-render, no server. See [below](#dynamic-recolouring-color_options). |
| **Overlay layers** | Bring your own geometry (zone polygons, POI circles, any lines) via `overlays=` — drawn under/over the roads, clickable, toggled from a **Layers** control. See [below](#overlay-layers-overlays). |
| **Boundary overlay** | An optional dashed outline (e.g. the clip area) drawn on top of the roads via `boundary=` — see [below](#boundary-overlay). |

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
rs.render_edges(edges, backend="web", basemap="dark_matter").save("city.html")
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
| `filter_col` | str | `None` | Column the filter panel lists/filters by, when it should differ from the styling `highway_col`. Default `None` = filter by the styling column. Set it to filter by a **source-native class** while widths/casing follow a different (e.g. OSM-highway proxy) column — the panel reads this raw property directly, so no restyle is needed. |
| `basemap_switcher` | bool | `True` | Show the in-map **base-layer dropdown** (its options come from `basemap` / `basemaps`). With `False` **plus an explicit `basemaps=` list**, the entries stay baked and addressable via `window.rsSetBasemap` for a custom UI; `False` alone bakes only the fixed backdrop. |
| `road_popup` | bool | `True` | Info popup shown when a road is **clicked** (lists the feature's attributes). Click-to-select works either way; set `False` to drive your own readout from `window.map` events. |
| `road_tooltip` | bool / list of cols | `False` | **Hover** tooltip: `True` = all attributes, a list of column names = only those, `False` = off. The shared `tooltip=` arg (folium backend / CLI `--tooltip`) is accepted as an **alias** — when given and `road_tooltip` is unset it drives this, so the same `tooltip=` / `--tooltip` call works on every backend. `road_tooltip` is the web-native name and wins if both are set. |
| `offset_frac` | float | `0.28` | Two-way lane offset as a fraction of the road's **pixel** width (pixel-proportional ⇒ constant overlap at every zoom). `0` = no lane split. |
| `width_frac` | float | `0.6` | Each two-way lane's width as a fraction of the full road width once the directions have fanned apart (a little over `0.5` so the two lanes overlap rather than leave a centre gap). |
| `offset_zoom` | int | `15` | Zoom at which lanes start fanning apart / splitting (ramped in over ~2 zoom levels). Below this the two directions stay coincident. |
| `tunnel_col` | str | `"tunnel"` | Column marking tunnels (used for `lvl`). |
| `bridge_col` | str | `"bridge"` | Column marking bridges. |
| `layer_col` | str | `"layer"` | OSM `layer` tag column (signed elevation when tunnel/bridge are absent). |
| `boundary` | geometry / GeoDataFrame / GeoJSON / `None` | `None` | Optional outline drawn on top of the roads — see [Boundary overlay](#boundary-overlay). |
| `color_options` | mapping / list / `None` | `None` | "Colour by" options baked for client-side recolouring + a dropdown — see [Dynamic recolouring](#dynamic-recolouring-color_options). |
| `overlays` | list of `Overlay` / `None` | `None` | Extra layers the caller brings (zones / POIs / lines) — see [Overlay layers](#overlay-layers-overlays). |

From the CLI these map to `--no-arrows` / `--no-labels` / `--no-filter` / `--no-basemap-switcher`.

## The JavaScript API (`window.rs*`)

Every in-map control is a thin UI over a global function, so custom pages can drive the map
directly. Each setter updates the map, keeps the built-in control in sync (if present), and
dispatches a CustomEvent on `document`:

| function | does | event |
|---|---|---|
| `rsSetBasemap(keyOrIdx)` | switch the base map (key, label, or index into `RS_BASEMAPS`) | `rs:basemapchange` |
| `rsSetClasses(list)` | show exactly these road classes, hide the rest | `rs:filterchange` |
| `rsSetColorField(nameOrIdx)` | switch the active `color_options` entry | `rs:colorchange` |
| `rsSetOverlay(labelOrIdx, on)` | show/hide one overlay | `rs:overlaychange` |
| `rsQuery(p => …)` | evaluate a predicate over every edge's columns → **id set** | — |
| `rsFilter(ids)` | show only these edges (`null` resets); ANDs with the class filter | `rs:filterchange` |
| `rsColor(ids, "#hex")` | paint the set one colour, layered over the active colour option (`null` resets) | `rs:colorchange` |
| `rsHighlight(ids)` | selection glow on the set (`[]` clears) | `rs:highlightchange` |
| `rsGetProps(ids)` | the rows behind the ids, internal fields stripped — table-ready | — |
| `rsFocus(ids, opt?)` | fly the camera to fit an id (or id set); `opt` merges into MapLibre's `fitBounds` (`padding` 80, `maxZoom` 17) | — |
| `rsSelect(id)` / `rsDeselect()` | select one edge exactly like a click (glow + popup/panel) / clear | `rs:select` / `rs:deselect` |
| `rsSetView3D(on)` | tilt to the settings' `camera.pitch_3d` / back to flat north-up | `rs:viewchange` |

The id sets use the roads source's generated feature ids — the same id space as `rs:select`
events. Labels, arrows and 3D deck ribbons sit on merged helper sources, so `rsFilter` prunes
road geometry but not those decorations (the class filter prunes everything).

Copyable UI templates built purely on this API live in the repo's `ui/` folder — start from
`ui/dashboard/` (query box → clickable results table → detail panel, plus a base-map select)
and make it yours.

Plus: `window.map` (the MapLibre `Map` — camera via `map.easeTo({pitch, bearing, ...})`),
click selection events `rs:select` / `rs:deselect`, and the registries `RS_BASEMAPS`,
`RS_CLASSES`, `RS_COLOR_OPTIONS`, `RS_OVERLAYS` for building your own controls. All of it works
with the built-in controls hidden (`basemap_switcher=False`, `filter_control=False`, …).

## Dynamic recolouring (`color_options`)

Bake **several pre-resolved "colour by" fill sets** into the one map and switch between them in the
browser — no re-render, no server round-trip. Pass `color_options`, an ordered mapping
`{name: {styler kwargs}}` (or a list of `{"name": ..., **kwargs}`), and the backend adds a **Colour
by** dropdown plus a legend that follows the active option. Each road keeps its width / casing /
lanes; only the **fill** swaps (via `setPaintProperty`). A neutral base reads best, so pair the
class option with `palette="mono"`:

```python
rs.render_edges(edges, backend="web", palette="mono",
    color_options={
        "Class": {},                                       # neutral mono base
        "AADT":  {"color_by": "aadt",  "cmap": "viridis"},
        "Speed": {"color_by": "speed_kph", "cmap": "magma"},
    },
).save("recolor.html")
```

Each option's value is the same data-driven kwargs you'd pass to `render_edges` (`color_by`,
`colors`, `cmap`, `vmin`, `vmax`, `width_by`, `palette`, `style`); an empty `{}` is the class style
on the base `palette`. The **first** option is active and drives the shared width/casing.

**Categorical option** — colour by a discrete field with an explicit `colors={value: hex}` map
instead of a `cmap` (values not in the map fall back to the base fill). Mixing continuous and
categorical options in one map is fine:

```python
rs.render_edges(edges, backend="web", palette="mono",
    color_options={
        "Class": {},                                                            # neutral mono base
        "Cover": {"color_by": "cover", "cmap": "RdYlGn", "vmin": 0, "vmax": 1},  # continuous ramp
        "State": {"color_by": "state",                                          # categorical
                  "colors": {"good": "#1baf7a", "mid": "#eda100", "weak": "#e34948"}},
    },
).save("recolor.html")
```

- **`cmap` accepts** any [branca](https://python-visualization.github.io/branca/) scheme name
  (`"viridis"`, `"YlOrRd"`, … — matched case-insensitively), any **matplotlib** colormap name
  including reversed `"_r"` variants (e.g. `"RdYlGn_r"`; the matplotlib fallback needs the `numeric`
  extra), or an explicit list of hex stops (`["#000", "#fff"]`). Set the numeric span with `vmin` / `vmax`.
- **Blank edges keep the base colour.** Where a data option has no value for an edge (NaN /
  unmapped), that edge falls back to the **base option's fill** — so on a `mono` base, "no data"
  roads keep their neutral mono colour instead of a flat grey.
- **Drive it from your own UI.** The page exposes `window.RS_COLOR_OPTIONS` (the baked options) and
  `window.rsSetColorField(name|index)` (recolour), and fires a `rs:colorchange` event on every
  switch — so a custom control can drive and follow the recolour. A worked custom-panel page is in
  [`examples/recolor_web_backend.py`](https://github.com/Khoshkhah/roadstyle/blob/main/examples/recolor_web_backend.py).

> The same `color_options` work on the [roadstyle.js spec page](embedding.md) (`to_spec` / `save` /
> `to_html`), where the richer `RoadStyleMap` API exposes `setColorField` / `getColorOptions` and a
> `colorchange` event.

## Overlay layers (`overlays`)

Bring extra geometry the caller owns — zone polygons, POI points, any lines — as a list of
[`Overlay`](parameters.md#8-overlay-extra-layers). Each becomes its own MapLibre source + layer(s),
placed **under** or **over** the roads, clickable for a popup of the fields you list, and toggled
from a **Layers** control. Overlays are passthrough data: *your* geometry with *your* style — they
do **not** go through roadstyle's road-styling compiler.

```python
rs.render_edges(edges, backend="web", palette="mono",
    overlays=[
        rs.Overlay(zones, kind="fill",   placement="under", color="#6aa9ff",
                   opacity=0.14, label="TAZ zones", popup=["taz_id", "name", "weight"]),
        rs.Overlay(pois,  kind="circle", placement="over",  color="#ff5d5d",
                   radius=7, label="POIs", popup=["name", "type"]),
    ],
).save("overlays.html")
```

`kind` is auto-detected from the geometry (polygon → `fill`+outline, point → `circle`, line →
`line`) but can be forced. `placement="under"` draws beneath the roads (e.g. zone fills), `"over"`
on top (e.g. POIs). Setting `popup` makes the overlay clickable (those fields show in the popup; an
empty list = decoration only). **Road clicks take precedence** — an overlay popup fires only where
the click misses every road. See [`Overlay`](parameters.md#8-overlay-extra-layers) for every field.

> **Overlays are single-colour.** An `Overlay` paints every feature with its one `color` — there is
> no per-feature `color_by` / `cmap` for overlay data. To colour features *by a value*, put that
> data on the **road edges** and use [`color_options`](#dynamic-recolouring-color_options);
> overlays are for bring-your-own geometry drawn in a flat colour. (For data-driven *points/lines*
> that aren't road edges, split them into one `Overlay` per colour bucket.)

## Boundary overlay

Pass `boundary=` to trace an area outline **on top of the roads** — typically the polygon the
network was clipped to, so the map shows its extent. It renders as a dashed violet line layer
(id `boundary`), separate from the road layers, so it is excluded from the road-class filter panel
and from hover/click picking.

It accepts whatever you have on hand and normalises it to a GeoJSON `FeatureCollection` in
EPSG:4326: a **shapely geometry**, a **`GeoSeries`/`GeoDataFrame`** (reprojected for you), or a
**GeoJSON mapping** (a geometry, `Feature`, or `FeatureCollection` — assumed already lon/lat). A
polygon's rings are stroked as lines. `None` (the default) draws nothing.

```python
from shapely.geometry import box

clip = box(18.04, 59.30, 18.10, 59.33)         # or a GeoDataFrame / GeoJSON dict
rs.render_edges(edges, backend="web", boundary=clip).save("clipped.html")
```

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


## Camera & 3D view

The starting camera is a **setting** (`camera` block: `pitch`, `bearing`, `pitch_3d`) with
per-call overrides:

```python
rs.render_edges(edges, pitch=55, bearing=-25)     # open tilted/rotated
rs.render_edges(edges, view_3d=True)              # tilted + extruded bridge decks
```

`view_3d=True` renders every bridge chain as a ramped 3D deck (`fill-extrusion`): connected
bridge edges are walked into one structure, ramps rise from the ground over `ramp_m`, forks stay
at full height, and the ribbon width matches the road width model at `bridge_decks.match_zoom`.
Decks are semi-transparent (`bridge_decks.opacity`), hover/select as ONE structure, and show the
same popup fields as flat edges. Every map also carries an on-map **2D/3D toggle** button and a
pitch-aware compass; no terrain/elevation data is used — the deck height is cartographic.

## Street names & arrows (annotation slots)

Each road chain is divided into equal `annotations.slot_m`-metre slots: street names take the
even slots, one-way arrows the odd ones — alternating along the road, never stacked. Unnamed
roads leave their name slots empty. Text/icon zoom ramps plus MapLibre's collision culling handle
density automatically; label/arrow colours live in the `labels` / `arrows` settings blocks.


## Roads vs. overlays — the architecture

The **road layer is the subject; overlays are annotations.** Both take their default styling
from the settings file, but they are entirely different machinery:

| | Roads (main layer) | Overlays |
|---|---|---|
| Styling | the full cartographic engine: palettes per class, zoom-scaled width curves, casing sandwich, draw-order ranks | one flat paint each — a single colour, opacity, width/radius |
| Structure | grade separation (tunnels faded below, bridges on top, 3D decks), two-way lane fanning, junction-sealed caps | none — a fill, a line, or circles |
| Annotations | street-name labels + one-way arrows in alternating slots | none |
| Data-driven colour | `color_by` ramps, `color_table`, the *Colour by* dropdown with legends | constant colour per overlay |
| Interaction | hover highlight, whole-bridge selection, popup/panel, `rs:select` events, class filter panel | hover tint + popup, visibility checkbox in the Layers toggle |
| Settings footprint | most of `defaults.json` (palettes, `roads` model, labels, arrows, slots, decks, camera) | the small `overlays` defaults block |
| Data contract | `highway` + the optional columns (see the README data contract) | any geometry; properties feed the popup only |

An overlay never grows casings or labels — by design, so the roads stay visually dominant and
overlays read as context. If a *second linear network* deserves road-grade treatment (e.g. NVDB
next to OSM), don't overlay it: render it **as** the main layer with a custom class vocabulary
(`highway_col=` + a registered palette).
