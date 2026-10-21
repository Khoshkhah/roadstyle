# Put it on a website

<p class="lead">Four ways to show a roadstyle map on a web page or in another map app, from no front-end code to your own map component.</p>

| way | Python at runtime? | use when |
|---|---|---|
| [The saved HTML in an iframe](#the-saved-html-in-an-iframe) | no | a static site, a report, a quick embed |
| [The JSON spec in your own map](#the-json-spec-in-your-own-map) | per request, or once for a static file | your Leaflet or MapLibre map draws the roads |
| [A roadstyle.js page](#a-roadstylejs-page) | no | a light Leaflet page with its own small JS API |
| [A style for other map apps](#a-style-for-other-map-apps) | once, to write the files | GeoLibre, RustGIS, QGIS or your MapLibre page opens the roads by URL |

In all four the browser needs no styling logic: each road carries its resolved style.

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

## A style for other map apps

`rs.export_style` writes the roads as a MapLibre style, vector tiles and a sprite: the roads only, with every column of the
edges in the tiles. Put the folder on a web server, then open it in GeoLibre (with the roadstyle plugin), RustGIS or any
MapLibre page. The base map is the app's own.

```python
rs.export_style("sodermalm/edges_driving.parquet", "out/sodermalm", base_url="https://example.org/sodermalm")
```

The input is a duckOSM GeoParquet file (`duckosm export-gis --format geoparquet`): the edges with their data and their drawing
positions. A file without the positions is an error that says how to save them. A GeoDataFrame works too.

| file | content |
|---|---|
| `style.json` | the roads' layers; every URL starts with `base_url` |
| `tiles/{z}/{x}/{y}.pbf` | the road tiles, every column (an id past 2^53 as text); `format="pmtiles"` writes one `roads.pmtiles` |
| `sprite.json`, `sprite.png` (and `@2x`) | the one-way arrow |

- `base_url` is the URL where the folder is served. The server must send `Access-Control-Allow-Origin: *`.
- Other keywords go to `render_edges` (`profile`, `palette`, `simple`, ...). `simple=False` (one layer per drawing position)
  draws best in RustGIS, which reads no `line-sort-key`.
- An app has no slider or menu: the page state (tunnel look, colour option) is baked at its start values.

**GeoLibre** (web or desktop), with the plugin in `geolibre-plugin/` on the branch `geolibre` of this repository (not on `main`: it is the plugin's own branch):

1. Settings › Manage Plugins › Settings › Manifest URLs: the URL of `geolibre-plugin/plugin.json` on your server, then Add.
2. Open the export: the menu **roadstyle** › Add a roadstyle layer, or the link `https://web.geolibre.app/?roadstyle=<URL of style.json>`.
3. The roads are one row in the Layers panel, over GeoLibre's base map: hide them there, or change the base map. A click on a
   road shows its data; the hover highlights it; a tilt shows the bridge decks in 3D.

The duckOSM GeoParquet file also opens alone, without the plugin, as a data layer in GeoLibre's own simple style:
`https://web.geolibre.app/?data=<URL of edges_driving.parquet>` (Identify shows the data).

To open all of a duckOSM database in one step, write its folder with `duckosm export-gis <db> -f geoparquet` and
put the folder on your server. Then use the menu **roadstyle** › Open a duckOSM folder, with the URL of the folder.
GeoLibre opens every file of the folder as a layer, and the plugin puts roadstyle's look on each edges layer.

To give such a data layer roadstyle's look (also a layer from a duckOSM `.duckdb` file), use the plugin:

1. Plugins › Installed › roadstyle: make the plugin active, if the menu **roadstyle** is not there.
2. The menu **roadstyle** › Style a layer with roadstyle, then type the number of the layer.
3. Accept the look URL (the plugin's `looks/default.json`) or type the URL of your own look from `rs.export_look(path)`.

The layer must have the columns `highway`, `oneway`, `tunnel`, `bridge`, `casing_level` and `fill_level` (duckOSM's
GeoParquet export has them). The look has the class colours, casings, the drawing positions, tunnels and two-way roads,
but no names, arrows or 3D decks. GeoLibre's own line of the layer becomes transparent; Identify still shows the data.

**RustGIS:** Home › Add › Basemap › Add Tile Layer with the `style.json` URL, or `?style=<URL>`. RustGIS puts the new layer
under its sample layers: clear their checkboxes. It does not draw `line-offset`, line labels or 3D
([what is lost](../design/style_export.md#what-you-lose-outside-roadstyles-page)).

**A local test:** the web apps are https pages; they read `http://localhost` only after you allow Chrome's local network access
(the icon left of the address bar › Site settings › Local network access).
