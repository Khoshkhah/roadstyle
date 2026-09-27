# Embedding maps in a website

roadstyle is a **Python library**: it runs in Python and produces maps or JSON. There are three
ways to get one of its maps onto a web page:

| Path | Who computes the style | Python at runtime? | Effort | Use when |
|---|---|---|---|---|
| **1. Baked HTML / iframe** | Python, once, ahead of time | No (a pre-generated file) | none | a static site, a report, a quick embed |
| **2. JSON API** | Python, per request | Yes (a server) | small | a live app whose data changes; your own Leaflet / MapLibre map draws it |
| **3. roadstyle.js spec page** | Python, baked into the spec | No (or a server for fresh specs) | small | roadstyle's own renderer inside your page, driven from your JavaScript |

In every path the browser never needs roadstyle's styling logic: each road's resolved style is
baked into per-feature `__rs_*` properties ([the JSON spec](#the-canonical-json-spec)), and the
browser only reads them.

**Which to use:**

- **No front-end code / just need it on a page** → Path 1. Prefer the `web` map
  (`render_edges(...).save(...)`): zoom-correct widths, two-way lanes, grade separation, 3D,
  offline. Its saved page is scriptable too (`window.rs*`), so a dashboard can be plain HTML
  built *around* it — see [the web-backend JS API](web-backend.md#the-javascript-api-windowrs) and
  the copyable [`ui/` templates](https://github.com/Khoshkhah/roadstyle/tree/main/ui).
- **A live app, data changes** → Path 2: a small endpoint returns `to_spec(...)`. Already have a
  Leaflet map → [the Leaflet snippet](#leaflet-your-own-map); vector tiles / GPU / lots of data →
  [the MapLibre snippet](#maplibre-gl-vector-webgl); a React/Vue app → feed `spec.geojson` to
  your map component with the same `__rs_*` accessors.
- **You want roadstyle's renderer but your own UI around it** (click handlers, a custom colour
  picker, side panels) → Path 3, the [`RoadStyleMap` API](#the-roadstylemap-js-api-events-recolour-custom-panels).

[Choosing an engine](engines.md) has the full feature matrix.

## What the outputs are

| Call | Returns | Use when |
|---|---|---|
| `render_edges(gdf).save("map.html")` | writes a file | the finished MapLibre (`web`) map — Path 1 |
| `to_spec(gdf, ...)` | `dict` (JSON) | you (or a frontend dev) will render it yourself |
| `to_geojson(gdf, ...)` | `dict` (FeatureCollection) | you only need the styled GeoJSON |
| `to_html(gdf, full=True)` | `str` (full page) | a complete roadstyle.js page |
| `to_html(gdf, full=False)` | `str` (`<div>+<script>`) | inject a roadstyle.js map into an existing page |
| `to_iframe(gdf)` | `str` (`<iframe srcdoc=…>`) | **easiest — no front-end code at all** |
| `save(gdf, "map.html", ...)` | writes a file | a standalone roadstyle.js map file |
| `save_spec(gdf, "map.json", ...)` | writes a file | the JSON for a frontend / API |

All of them take the same styling arguments as [`render_edges`](parameters.md) (`color_by`,
`cmap`, `colors`, `width_by`, …).

## The canonical JSON spec

```python
import roadstyle as rs
spec = rs.to_spec(edges, color_by="aadt", cmap="viridis", basemap="dark_matter")
rs.save_spec(edges, "roads.json", color_by="aadt", cmap="viridis")
```

```jsonc
{
  "roadstyle": "spec/1",
  "crs": "EPSG:4326",
  "bounds": [[minLat, minLon], [maxLat, maxLon]],
  "render": { "sandwich": true, "line_cap": "round", "line_join": "round" },
  "basemap": { "key": "dark_matter", "url": "...", "attr": "...", "is_dark": true },
  "basemaps": [ /* the same shape — base maps offered to the in-map switcher */ ],
  "tooltip": ["name", "aadt"],
  "legend": { "kind": "continuous", "title": "aadt", "vmin": 0, "vmax": 25000, "ramp": ["#440154", ...] },
  "color_options": [ /* present only with color_options= : one entry per "colour by" option */
    { "name": "Class", "prop": "__rs_fill",    "legend": null },
    { "name": "AADT",  "prop": "__rs_fill__1", "legend": { "kind": "continuous", ... } } ],
  "color_active": 0,
  "geojson": { "type": "FeatureCollection", "features": [ /* each feature.properties carries: */ ] }
}
```

Each feature's `properties` carry the **baked-in resolved style** — your frontend just reads them,
it doesn't need roadstyle's logic:

| property | meaning |
|---|---|
| `__rs_fill` | fill (centre-line) colour |
| `__rs_w` | fill width (px) |
| `__rs_op` | fill opacity |
| `__rs_dash` | dash pattern (or null) |
| `__rs_casing` | resolved casing colour (or null; one per edge, constant on every base map) — **what every backend draws** |
| `__rs_cw` | casing width (px) |
| `__rs_cop` | casing opacity |
| `__rs_class` | road class / category |
| `__rs_fill__1`, `__rs_fill__2`, … | extra fill colours, one per `color_options` entry (the renderer swaps which one the fill reads) |

> **Render order = the geometry sandwich.** Draw a casing layer first (using `__rs_casing`/`__rs_cw`),
> then the fill layer on top (`__rs_fill`/`__rs_w`). That keeps road borders from slicing through
> higher roads.

---

## Path 1 — baked HTML / iframe

Python writes a finished, self-contained map; you drop it into a page. No frontend code, no
server. `to_iframe` returns an `<iframe>` you paste anywhere:

```python
html = rs.to_iframe(edges, color_by="aadt", cmap="viridis", height="600px")
```

Or save a file and point an `<iframe>` at it — the `web` map or a roadstyle.js page:

```python
rs.render_edges(edges, color_by="aadt", cmap="viridis").save("roads.html")   # web (MapLibre)
rs.save(edges, "roads.html", color_by="aadt", cmap="viridis")                # roadstyle.js page
```
```html
<iframe src="roads.html" style="width:100%;height:600px;border:0;"></iframe>
```

Trade-off: the map is a snapshot — to show new data, re-run Python and regenerate the file.

## Path 2 — JSON API (Python serves, JavaScript draws)

A small endpoint calls `to_spec()` and returns the styled JSON; your browser map fetches and
draws it. Python still computes the styling, so roadstyle stays the single source of truth for
the cartography. Usually the most practical path for a live app (filters, uploads, fresh traffic).

```
Browser  ──GET /roads.json──▶  Python API  ──▶  roadstyle.to_spec(edges, ...)
Browser  ◀──── styled JSON ───  (a dict with geojson + __rs_* props + legend + basemap)
Leaflet / MapLibre / deck.gl draws it
```

With FastAPI (Flask / Django are equivalent — return the dict as JSON):

```python
# server.py
from fastapi import FastAPI
import geopandas as gpd
import roadstyle as rs

app = FastAPI()
edges = gpd.read_file("edges.gpkg")          # or load per request / from a DB

@app.get("/roads.json")
def roads(color_by: str = "aadt", cmap: str = "viridis"):
    return rs.to_spec(edges, color_by=color_by, cmap=cmap, basemap="dark_matter")
```

A static page can load a `save_spec` file the same way, with no server.

### Leaflet (your own map)

Fetch the spec, then style each feature from its `__rs_*` props:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
<div id="map" style="height:600px"></div>
<script>
fetch("roads.json").then(r => r.json()).then(spec => {
  const map = L.map("map");
  const bm = spec.basemap;
  L.tileLayer(bm.url, {attribution: bm.attr, subdomains: bm.subdomains, maxZoom: 20}).addTo(map);

  // casing under …
  L.geoJSON(spec.geojson, {style: f => {
    const p = f.properties;
    return p.__rs_casing && p.__rs_cw
      ? {color: p.__rs_casing, weight: p.__rs_cw, opacity: p.__rs_cop, lineCap:"round", lineJoin:"round"}
      : {opacity: 0, weight: 0};
  }}).addTo(map);

  // … fill over (the geometry sandwich)
  L.geoJSON(spec.geojson, {style: f => {
    const p = f.properties;
    return {color: p.__rs_fill, weight: p.__rs_w, opacity: p.__rs_op,
            dashArray: p.__rs_dash, lineCap:"round", lineJoin:"round"};
  }}).addTo(map);

  map.fitBounds(spec.bounds);
});
</script>
```

### MapLibre GL (vector / WebGL)

Add the spec's GeoJSON as a source and two line layers reading the `__rs_*` props via
`["get", ...]` expressions:

```html
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css"/>
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
<div id="map" style="height:600px"></div>
<script>
fetch("roads.json").then(r => r.json()).then(spec => {
  const bm = spec.basemap;
  const map = new maplibregl.Map({
    container: "map",
    style: {                       // a minimal raster basemap from the spec
      version: 8,
      sources: { bg: { type: "raster", tiles: [bm.url.replace("{s}", "a")], tileSize: 256, attribution: bm.attr } },
      layers: [{ id: "bg", type: "raster", source: "bg" }]
    }
  });
  map.on("load", () => {
    map.addSource("roads", { type: "geojson", data: spec.geojson });
    map.addLayer({ id: "casing", type: "line", source: "roads",
      paint: { "line-color": ["get","__rs_casing"], "line-width": ["get","__rs_cw"],
               "line-opacity": ["get","__rs_cop"] },
      layout: { "line-cap": "round", "line-join": "round" } });
    map.addLayer({ id: "fill", type: "line", source: "roads",
      paint: { "line-color": ["get","__rs_fill"], "line-width": ["get","__rs_w"],
               "line-opacity": ["get","__rs_op"] },
      layout: { "line-cap": "round", "line-join": "round" } });
    map.fitBounds([spec.bounds[0].slice().reverse(), spec.bounds[1].slice().reverse()]);
  });
});
</script>
```

> MapLibre wants `[lon, lat]`; the spec's `bounds` are `[lat, lon]` (Leaflet order), hence the
> `.reverse()`. Spec widths are fixed pixels; only the `web` backend scales widths per zoom.

## Path 3 — the roadstyle.js spec page

`to_html` / `save` / `to_iframe` inline a small renderer, `roadstyle.js`, that draws a spec. It
reads the baked `__rs_*` props (it does not recompute styling) and exposes a JavaScript API,
`RoadStyleMap`, so your page can react to it and drive it.

### Reacting to a selection (click → your code)

`roadstyle.js` hands clicks back to your page so a custom UI can react. Register handlers in
JavaScript (an `interaction_config.json` can't carry functions):

```js
const m = new RoadStyleMap("map");
m.on("select", (feature, layer) => {
  // feature.properties carries __rs_class plus your original data columns
  console.log("selected", feature.properties);
});
m.on("deselect", (prevFeature) => console.log("cleared"));
await m.load("map_data.json");

// or poll instead of using callbacks:
const current = m.getSelection();   // the selected feature, or null
```

Selection is **single** — clicking another road replaces it; click the same road again, or click
the map background, to deselect (each fires `onDeselect`). You can also pass the handlers up front:
`new RoadStyleMap("map", { onSelect, onDeselect })`.

### The `RoadStyleMap` JS API (events, recolour, custom panels)

The built-in widgets are opt-in via `widgets`, but you can also build your **own** UI on top.

**Event bus.** `on(event, fn)` / `off(event, fn)` subscribe to map events; several listeners per
event are fine (the legacy `onSelect`/`onDeselect` options still fire alongside them):

| event | fired with | when |
|---|---|---|
| `ready` | `(map, spec)` | after the map has loaded and rendered |
| `select` / `deselect` | `(feature, layer)` / `(prevFeature)` | a road is selected / the selection cleared |
| `colorchange` | `(option, index)` | the active "colour by" option changed |

**Switchable colouring.** Bake the options in Python with
[`color_options`](web-backend.md#dynamic-recolouring-color_options) (works on `to_spec` / `save` /
`to_html` too), then drive them client-side:

```js
m.getColorOptions();        // [{name, prop, legend}, …] baked into the spec
m.setColorField("AADT");    // recolour by name or index — no re-render; swaps the legend
m.getColorField();          // the active option's index
```

Turn the built-in picker on with `widgets: { colors: true }`, or build your own and call
`setColorField`.

**Custom panels.** `addPanel` gives you styled, auto-stacking chrome in any corner; fill it and wire
it to the API:

```js
const m = RoadStyle.create("map", spec, { widgets: { colors: false } });
m.on("ready", map => {
  map.addPanel({ title: "Colour by", position: "topright", render(body, map) {
    map.getColorOptions().forEach((o, i) => {
      const b = document.createElement("button");
      b.textContent = o.name; b.onclick = () => map.setColorField(i);
      body.appendChild(b);
    });
    map.on("colorchange", (opt, idx) => { /* keep your buttons in sync */ });
  }});
});
```

`addPanel({ position, title, collapsible, render(body, map) })` returns `{ el, body, remove() }`.
A worked page is in
[`examples/recolor_custom_panel.py`](https://github.com/Khoshkhah/roadstyle/blob/main/examples/recolor_custom_panel.py).

> The **`web` (MapLibre) map** is not a `RoadStyleMap` — it has its own, larger JS surface:
> `window.rs*` setters for every control (`rsSetBasemap`, `rsSetClasses`, `rsSetColorField`,
> `rsSetOverlay`, `rsSetView3D`, `rsSelect`/`rsDeselect`), the id-set query verbs
> (`rsQuery` → `rsFilter`/`rsColor`/`rsHighlight`/`rsGetProps`/`rsFocus`), and `rs:*`
> CustomEvents. See [the web-backend JS API](web-backend.md#the-javascript-api-windowrs).

## Not planned: a JavaScript styling port

A browser-only roadstyle — the styling *logic* (palettes, the geometry sandwich, class → colour and
numeric ramps) reimplemented in JavaScript, with no Python anywhere — would be a separate project
(e.g. an npm package), not something this library emits. The groundwork exists: palette JSON
(`save_palette`) is language-neutral and the `spec/1` / `__rs_*` contract is stable. It is only
worth building if a JS-only runtime is a hard requirement; paths 1–3 cover everything else.
