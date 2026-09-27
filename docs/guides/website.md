# Put it on a website

<p class="lead">Three ways to show a roadstyle map on a web page, from no front-end code to your own map component.</p>

| way | Python at runtime? | use when |
|---|---|---|
| [The saved HTML in an iframe](#the-saved-html-in-an-iframe) | no | a static site, a report, a quick embed |
| [The JSON spec in your own map](#the-json-spec-in-your-own-map) | per request, or once for a static file | your Leaflet or MapLibre map draws the roads |
| [A roadstyle.js page](#a-roadstylejs-page) | no | a light Leaflet page with its own small JS API |

In all three the browser needs no styling logic: each road carries its resolved style.

## The saved HTML in an iframe

The default map is one offline file. Save it and point an iframe at it. It keeps everything:
zoom-scaled widths, labels, 3D, the `window.rs*` API.

```python
rs.render_edges(edges).save("roads.html")
```

```html
<iframe src="roads.html" style="width:100%;height:600px;border:0"></iframe>
```

The map is a snapshot: re-run Python to show new data.

## The JSON spec in your own map

`rs.to_spec` returns a dict: the edges as GeoJSON, each with its style baked in, plus the base
map, bounds and legend. Save it for a static page, or return it from a web endpoint.

```python
spec = rs.to_spec(edges, color_by="maxspeed_kmh", cmap="viridis")
rs.save_spec(spec, "roads.json")        # or: roadstyle edges.gpkg -f spec -o roads.json
```

Draw it with two line layers, casing first, then fill (Leaflet shown; MapLibre reads the same
properties with `["get", "__rs_fill"]`):

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
<div id="map" style="height:600px"></div>
<script>
fetch("roads.json").then(r => r.json()).then(spec => {
  const map = L.map("map").fitBounds(spec.bounds);
  L.tileLayer(spec.basemap.url, {attribution: spec.basemap.attr}).addTo(map);
  const line = (c, w, o) => f => { const p = f.properties;
    return {color: p[c], weight: p[w], opacity: p[c] ? p[o] : 0, lineCap: "round", lineJoin: "round"}; };
  L.geoJSON(spec.geojson, {style: line("__rs_casing", "__rs_cw", "__rs_cop")}).addTo(map);
  L.geoJSON(spec.geojson, {style: line("__rs_fill", "__rs_w", "__rs_op")}).addTo(map);
});
</script>
```

Every feature carries:

- `__rs_fill`, `__rs_w`, `__rs_op`, `__rs_dash`: the fill colour, width (px), opacity and dash.
- `__rs_casing`, `__rs_cw`, `__rs_cop`: the casing colour (or null), width and opacity.
- `__rs_class`: the road class; with `color_options`, `__rs_fill__1`, `__rs_fill__2`, ... hold
  one fill colour per option.

Widths are fixed pixels; only the default map scales them with zoom. `fetch` needs the page
served (`python -m http.server`), not opened from disk.

## A roadstyle.js page

`rs.save` writes a Leaflet page with a small bundled renderer, `roadstyle.js`, and its
`RoadStyleMap` API (`on("select")`, `setColorField`, `addPanel`). `rs.to_iframe` returns the
same page as an `<iframe srcdoc>` string to paste anywhere.

```python
rs.save(edges, "roads.html", color_by="maxspeed_kmh", cmap="viridis")
html = rs.to_iframe(edges, height="600px")
```

Most custom pages are easier as the default map plus your own panel:
see [Dashboards & JavaScript](dashboards.md).

**See also:** [Every parameter](../reference/parameters.md) · [JavaScript API](../reference/javascript.md)
