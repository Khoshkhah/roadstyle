# Embedding maps in a website

roadstyle can output a **stack-agnostic JSON spec** (`to_spec`) plus ready-to-use HTML, so you
can put a styled road map into any web page — from "drop in an iframe, write zero code" to
"feed the JSON to my own Leaflet / MapLibre frontend".

## What the outputs are

| Call | Returns | Use when |
|---|---|---|
| `to_spec(gdf, ...)` | `dict` (JSON) | you (or a frontend dev) will render it yourself |
| `to_geojson(gdf, ...)` | `dict` (FeatureCollection) | you only need the styled GeoJSON |
| `to_html(gdf, full=True)` | `str` (full page) | you want a complete `.html` page |
| `to_html(gdf, full=False)` | `str` (`<div>+<script>`) | you want to inject a map into an existing page |
| `to_iframe(gdf)` | `str` (`<iframe srcdoc=…>`) | **easiest — no front-end code at all** |
| `save(gdf, "map.html", ...)` | writes a file | a standalone interactive map file |
| `save_spec(gdf, "map.json", ...)` | writes a file | the JSON for a frontend / API |

All of them take the same styling arguments as
[`render_edges`](parameters.md#2-render_edges-the-main-entry-point) (`color_by`, `cmap`,
`colors`, `width_by`, `theme`, …).

## The canonical JSON spec

```python
import roadstyle as rs
spec = rs.to_spec(edges, color_by="aadt", cmap="viridis", theme="dark")
rs.save_spec(edges, "roads.json", color_by="aadt", cmap="viridis")
```

```jsonc
{
  "roadstyle": "spec/1",
  "crs": "EPSG:4326",
  "theme": "dark",
  "bounds": [[minLat, minLon], [maxLat, maxLon]],
  "render": { "sandwich": true, "line_cap": "round", "line_join": "round" },
  "basemap": { "key": "dark_matter", "url": "...", "attr": "...", "is_dark": true },
  "tooltip": ["name", "aadt"],
  "legend": { "kind": "continuous", "title": "aadt", "vmin": 0, "vmax": 25000, "ramp": ["#440154", ...] },
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
| `__rs_casing` | casing colour for this theme (or null) |
| `__rs_cw` | casing width (px) |
| `__rs_cop` | casing opacity |
| `__rs_class` | road class / category |

> **Render order = the geometry sandwich.** Draw a casing layer first (using `__rs_casing`/`__rs_cw`),
> then the fill layer on top (`__rs_fill`/`__rs_w`). That keeps road borders from slicing through
> higher roads.

---

## Option 1 — iframe (no front-end code)

The simplest path. `to_iframe` returns a self-contained `<iframe>` you paste anywhere.

```python
html = rs.to_iframe(edges, color_by="aadt", cmap="viridis", height="600px")
# paste `html` into your page, or write it to a template
```

Or save a standalone file and point an `<iframe>` at it:

```python
rs.save(edges, "roads.html", color_by="aadt", cmap="viridis")
```
```html
<iframe src="roads.html" style="width:100%;height:600px;border:0;"></iframe>
```

## Option 2 — Leaflet (your own map)

Serve the spec JSON, then style each feature from its `__rs_*` props:

```html
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
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

## Option 3 — MapLibre GL (vector / WebGL)

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
> `.reverse()`. A future roadstyle option may emit a zoom→width curve as a MapLibre
> `["interpolate", ["linear"], ["zoom"], …]` expression for `line-width` (see
> [parameters](parameters.md) — widths are fixed pixels today).

---

## Which option for you?

- **No front-end experience / just need it on a page** → **Option 1 (iframe)**.
- **You already have a Leaflet map** → **Option 2**.
- **You use vector tiles / want GPU rendering / lots of data** → **Option 3 (MapLibre)**.
- **A React/Vue app** → fetch the spec and feed `spec.geojson` to your map component using the
  same `__rs_*` accessors shown above.


## Reacting to a selection (click → your code)

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
