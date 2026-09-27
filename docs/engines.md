# Choosing an engine

roadstyle can draw the same styled network four ways. They share the styling compiler (palettes,
widths, the casing+fill sandwich, data-driven colour) — what differs is **who renders it and
where it runs**. This page is the decision guide, and [below](#roadstyle-vs-other-tools) how
roadstyle compares with other tools.

## The four engines

| Engine | What it is | One line |
|---|---|---|
| **`web`** (default) | a finished MapLibre vector map in one self-contained HTML file | *the map as a product* |
| **`folium`** | a Leaflet map via the folium ecosystem | *the map inside a folium workflow* |
| **`lonboard`** | a GPU/WebGL map (deck.gl) in the notebook | *the map at big-data scale* |
| **roadstyle.js / spec** | styled JSON (`to_spec`) + a small JS renderer for **your own page** | *the map inside your web app* |

```python
import geopandas as gpd
import roadstyle as rs
edges = gpd.read_file("edges.gpkg")

rs.render_edges(edges)                                   # web (default)
rs.render_edges(edges, backend="folium")                 # folium / Leaflet
rs.render_edges(edges, backend="lonboard")               # GPU, big data
spec = rs.to_spec(edges, color_by="aadt", cmap="viridis")  # JSON for your own frontend
```

## Feature matrix

| | `web` | `folium` | `lonboard` | spec + roadstyle.js |
|---|---|---|---|---|
| Per-zoom road widths (osm-carto curve) | ✅ | — (fixed px) | — (fixed px) | — (fixed px) |
| Two-way lanes, one-way arrows, street names | ✅ | — | — | — |
| Tunnel/bridge grade separation | ✅ | draw order only | — | draw order only |
| **3D view** (tilted camera, extruded cased bridge decks) | ✅ | — | — | — |
| Hover / click-select / popup or side panel | ✅ | tooltip + pin | hover tooltip | select events |
| Base-map switcher (incl. tile-less `blank`) | ✅ | thumbnail switcher | fixed | from the spec |
| Client-side recolouring (`color_options`) | ✅ dropdown | — | — | ✅ `setColorField` |
| **JavaScript API** (setters, id-set queries, events) | ✅ `window.rs*` | — | — | ✅ `RoadStyleMap` (smaller) |
| Overlays (your zones / POIs / lines) | ✅ | via folium | — | — |
| Offline single file (no server, no internet) | ✅ (`blank` = zero requests) | ✅ (tiles need net) | notebook only | ✅ page or served |
| Comfortable data size | ~10⁴ inline; **~10⁵ with `tiles=True`** (embedded PMTiles) | ~10³–10⁴ | **10⁵–10⁶+** | like `web` |
| Legends for data-driven colour | ✅ | ✅ | — (`legend=` accepted, not drawn) | ✅ |
| Pre-highlighted `selected=` edges | — (click instead) | ✅ | — | — |

## Which to use

- **Start with `web`.** It's the default for a reason: the full cartographic engine, interactive,
  one offline file, and scriptable afterwards (`window.rs*` + the [`ui/` templates](https://github.com/Khoshkhah/roadstyle/tree/main/ui)).
  If you don't have a specific reason below, this is the answer. It also beats the spec path for
  most dashboards: build the dashboard *around* the saved page with plain HTML (see
  [`ui/dashboard`](https://github.com/Khoshkhah/roadstyle/tree/main/ui/dashboard)) and skip writing
  a renderer.
- **Use `folium`** when the map must live *inside an existing folium/Leaflet workflow* — you're
  composing with folium plugins, or you want the `selected=` pre-highlight and the pin-tooltip
  behaviour. Accept fixed-pixel widths and no labels/arrows/3D.
- **Use `lonboard`** when the bottleneck is *size*: hundreds of thousands of edges explored
  interactively in a notebook. Accept simpler styling (colour + width per edge; no casing
  sandwich, labels, legend or selection UI). Same `render_edges` call, different `backend=`, so
  find the story in `lonboard` at scale, then ship the styled subset with `web`.
- **Use `to_spec` / roadstyle.js** only when the map must integrate into *an existing JS app's own
  map component*: a server renders fresh JSON per request, or a static page loads a saved spec, and
  your Leaflet/MapLibre/React code draws it — roadstyle stays the single source of styling truth
  via the baked `__rs_*` properties. See [Embedding](embedding.md).

## roadstyle vs other tools

roadstyle isn't trying to replace the geospatial-viz ecosystem — it's an **opinionated road
cartography layer** on top of it.

| Tool | Interactive? | Road **casing** + per-class widths | Colour by **data** | Web-embeddable output | Best for |
|---|---|---|---|---|---|
| **roadstyle** | ✅ MapLibre (`web`) + folium + lonboard | ✅ built-in (geometry sandwich; per-zoom widths on `web`) | ✅ categorical + numeric | ✅ HTML / iframe / JSON spec | correct interactive road maps, out of the box |
| geopandas `.explore()` | ✅ folium | ❌ single line, no casing/z-order | ✅ (`column`, `cmap`, `scheme`) | ⚠️ folium HTML only | quick data exploration of any geometry |
| prettymaps | ❌ static PNG/SVG | ✅ per-class widths | ❌ class only | ❌ image | poster-quality static art maps |
| osmnx `plot_graph` | ❌ mostly static | ⚠️ basic | ⚠️ manual | ❌ | street-network analysis |
| kepler.gl | ✅ deck.gl GUI | ❌ flat strokes | ✅ (full GUI, time playback) | ⚠️ needs the app / a token | exploring any geodata visually |
| raw MapLibre / Mapbox styles | ✅ | ✅ (you author it) | ✅ (you author it) | ✅ | full custom vector basemaps |

**vs geopandas `.explore()`.** The closest neighbour — it already does data-driven colouring
(`column=`, `cmap=`, `scheme=`), legends and tooltips. It draws a single flat line, though.
roadstyle adds the road cartography: the **geometry sandwich** (a casing under every fill, drawn in
importance order, so junctions read cleanly), **per-class widths** (motorway wider than
residential), OSM treatments (tunnel fade, bridge casing, `_link` narrowing, dashed paths), an
in-map base-map switcher, and output that embeds outside folium. Use `.explore()` for a fast look
at arbitrary geometry; roadstyle when the output is a *road map* you care about the look of, or
that ships to a website.

**vs prettymaps.** prettymaps makes gorgeous **static** maps (osmnx + matplotlib) for print and
posters. roadstyle is for **interactive / web** maps and **data-driven** colouring
(traffic, speed, congestion).

**vs kepler.gl.** [kepler.gl](https://kepler.gl/) is a general-purpose *exploration* GUI on
deck.gl: drag-drop a CSV/GeoJSON, pick layers (points, arcs, lines, hexbins, trips), filter with
time playback. It's the right tool for *"what's in this dataset?"* and the wrong one for road
cartography: lines are flat strokes, so no casing sandwich, no per-zoom per-class widths, no
street labels, no one-way arrows, no grade separation — roads read as coloured spaghetti. Data
moves freely one way: any roadstyle input is kepler.gl-ready via `roadstyle edges.gpkg -f geojson`
(or the GeoDataFrame straight into the [`keplergl`](https://docs.kepler.gl/docs/keplergl-jupyter)
Jupyter widget), then drag it into [kepler.gl/demo](https://kepler.gl/demo). The styling doesn't
transfer — that's the part roadstyle exists for.

**vs raw MapLibre.** The `web` backend *is* a MapLibre map: roadstyle generates the style (casing
and fill layers per class, the osm-carto zoom→width curve, grade-separated draw order, labels,
arrows, 3D decks) and inlines the data and a `window.rs*` API. Writing that style yourself gives
full control over a vector basemap; roadstyle gives you the road part in one call.

### What roadstyle reuses

roadstyle doesn't reinvent the wheels under it — it builds on
[`branca`](https://python-visualization.github.io/branca/) (colormaps + legends),
[`mapclassify`](https://pysal.org/mapclassify/) (numeric classification schemes, `numeric`
extra) and [`xyzservices`](https://github.com/geopandas/xyzservices) (tile providers, `basemaps`
extra), so your knowledge of those libraries carries over.

### Known limitations

- **Fixed-pixel widths on folium, lonboard and the spec** — fine at city scale, can blob at very
  wide zoom. Only `web` scales widths per zoom (the osm-carto curve).
- **No lonboard legends** — `legend=` is accepted for API parity but not drawn; folium, `web` and
  the spec have them.
- **Everything ships in one file** — a saved `web` map carries its data (gzipped by default;
  comfortable to ~10⁴ edges). For bigger networks `tiles=True` embeds a PMTiles vector tileset
  instead, and ~10⁵ edges boot in seconds
  ([web backend](web-backend.md#vector-tiles-in-the-file-tilestrue)). A *hosted* tile server for
  county-scale-and-up data is out of scope; `lonboard` covers raw very-large rendering.
