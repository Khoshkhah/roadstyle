# Choosing an engine

roadstyle can draw the same styled network four ways. They share the styling compiler (palettes,
widths, the casing+fill sandwich, data-driven colour) — what differs is **who renders it and
where it runs**. This page is the decision guide.

## The four engines

| Engine | What it is | One line |
|---|---|---|
| **`web`** (default) | a finished MapLibre vector map in one self-contained HTML file | *the map as a product* |
| **`folium`** | a Leaflet map via the folium ecosystem | *the map inside a folium workflow* |
| **`lonboard`** | a GPU/WebGL map (deck.gl) in the notebook | *the map at big-data scale* |
| **roadstyle.js / spec** | styled JSON (`to_spec`) + a small JS renderer for **your own page** | *the map inside your web app* |

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
| Comfortable data size | ~10⁴–10⁵ edges (`compress` is on by default) | ~10³–10⁴ | **10⁵–10⁶+** | like `web` |
| Legends for data-driven colour | ✅ | ✅ | ✅ | ✅ |
| Pre-highlighted `selected=` edges | — (click instead) | ✅ | — | — |

## Rules of thumb

- **Start with `web`.** It's the default for a reason: the full cartographic engine, interactive,
  one offline file, and scriptable afterwards (`window.rs*` + the [`ui/` templates](https://github.com/Khoshkhah/roadstyle/tree/main/ui)).
  If you don't have a specific reason below, this is the answer.
- **Use `folium`** when the map must live *inside an existing folium/Leaflet workflow* — you're
  composing with folium plugins, or you want the `selected=` pre-highlight and the pin-tooltip
  behaviour. Accept fixed-pixel widths and no labels/arrows/3D.
- **Use `lonboard`** when the bottleneck is *size*: hundreds of thousands of edges explored
  interactively in a notebook. Accept simpler styling (colour + width per edge; no casing
  sandwich, labels, or selection UI).
- **Use `to_spec` / roadstyle.js** when *your web app owns the page*: a server renders fresh JSON
  per request (`FastAPI` + `to_spec`), or a static page loads a saved spec, and your own
  Leaflet/MapLibre/React code draws it — roadstyle stays the single source of styling truth via
  the baked `__rs_*` properties. See [Frontend integration](frontend.md) and
  [Embedding](embedding.md).

Two combinations worth knowing:

- **`web` + custom UI beats spec for most dashboards** — since the saved `web` page exposes the
  full `rs*` JavaScript API (queries, filtering, recolouring, selection, camera), you can build a
  dashboard *around* it with plain HTML (see [`ui/dashboard`](https://github.com/Khoshkhah/roadstyle/tree/main/ui/dashboard))
  and skip writing a renderer entirely. Reach for the spec path only when the map must integrate
  into an existing JS app's own map component.
- **`lonboard` for exploration, `web` for the deliverable** — same `render_edges` call, different
  `backend=`; find the story at scale, then ship the styled subset.

## The same call, four ways

```python
import geopandas as gpd
import roadstyle as rs
edges = gpd.read_file("edges.gpkg")

rs.render_edges(edges)                                   # web (default)
rs.render_edges(edges, backend="folium")                 # folium / Leaflet
rs.render_edges(edges, backend="lonboard")               # GPU, big data
spec = rs.to_spec(edges, color_by="aadt", cmap="viridis")  # JSON for your own frontend
```
