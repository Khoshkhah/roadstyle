# Tutorial

A guided, read-it-top-to-bottom walkthrough of roadstyle — the same ground the
[example notebooks](examples.md) cover, but on one page so you can learn it in the browser without
opening Jupyter. Every snippet is copy-paste runnable; they all use a `GeoDataFrame` of road edges
called `edges` (any road dataset with line geometry and a road-class column works).

!!! tip "How to follow along"
    Install with `pip install -e ".[numeric,basemaps]"` and load any road dataset. The notebooks
    ship a sample (`notebooks/data/sundbyberg_edges.gpkg`, ~4,000 real edges); to reproduce a step
    exactly, open the matching notebook listed under each section.

---

## 1 · Quickstart

roadstyle turns a `GeoDataFrame` of roads into a styled, interactive map — an OSM-style *geometry
sandwich* (a coloured fill drawn over a wider casing) so junctions and overlaps read cleanly. You
need just two things: a **road-class column** (default `highway`) and **line geometry**.

```python
import geopandas as gpd
import roadstyle as rs

edges = gpd.read_file("edges.gpkg")        # any CRS; reprojected to EPSG:4326 for you
print(f"{len(edges):,} edges, CRS {edges.crs}")
```

One call renders it. In a notebook the returned `folium.Map` displays inline; anywhere else,
`.save()` it:

```python
m = rs.render_edges(edges, theme="dark")   # high-saturation palette on a dark base map
m.save("roads.html")                        # a standalone, self-contained page
```

That's the whole loop: **load → `render_edges` → `.save`**. Everything below adds colour, filtering,
and web output on top of it.

> Notebook: **01 · Quickstart**

---

## 2 · Themes & palettes

Two palettes — `highsat` (high-contrast) and `carto` (classic OSM) — and three themes: `light`,
`dark`, and `satellite`.

```python
rs.render_edges(edges, palette="carto", theme="light")
rs.render_edges(edges, palette="highsat", theme="dark")
```

Themes set the base map and casing colours; palettes set the per-road-class colours. See
[Palettes](palettes.md) and [Themes](themes.md) for the full reference.

> Notebook: **01 · Quickstart**, **06 · Customizing the look**

---

## 3 · Colour roads by your own data

Beyond road class, you can colour and size edges by **any** column — categorical or numeric — with
automatic legends.

### Categorical (`color_by` + `colors`)

Give each category an explicit colour. Here we derive an importance class from the `highway` tag:

```python
major  = {"motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link"}
medium = {"secondary", "tertiary", "secondary_link", "tertiary_link"}
edges["importance"] = edges["highway"].apply(
    lambda h: "major" if h in major else "medium" if h in medium else "minor"
)

rs.render_edges(
    edges,
    color_by="importance",
    colors={"major": "#ef4444", "medium": "#f59e0b", "minor": "#64748b"},
    legend=True,
)
```

### Numeric (`color_by` + `cmap` + `width_by`)

Map a number to a colour ramp **and** a line-width ramp. Any branca/matplotlib colormap name works
for `cmap`; `vmin`/`vmax` clamp the colour range; `width_by=(min, max)` scales width with the value.

```python
edges["length_m"] = edges.to_crs(3006).length.round(1)   # metres, via a projected CRS

rs.render_edges(
    edges,
    color_by="length_m",
    cmap="viridis",
    width_by=(1, 6),        # thinnest .. thickest pixel width across the value range
    vmin=0, vmax=2000,
    legend=True,
)
```

!!! note "Numeric styling needs an extra"
    `cmap`/numeric classification uses `mapclassify` + `matplotlib`: `pip install "roadstyle[numeric]"`.

> Notebook: **02 · Data-driven styling**

---

## 4 · Filtering & highlighting

Show only the road types you care about, and highlight a selection on top of the map.

```python
sorted(rs.highway_types(edges))                       # what classes are present?

# keep or drop types — match_links=True (default) keeps *_link ramps with their parent
rs.render_edges(edges, include=["motorway", "trunk", "primary"], theme="dark")
rs.render_edges(edges, exclude=["service", "footway", "path", "cycleway"], theme="light")

# highlight a sub-selection with a neon overlay
sel = edges[edges["highway"] == "secondary"]
rs.render_edges(edges, theme="dark", selected=sel)
```

> Notebook: **03 · Filtering & highlighting**

---

## 5 · Customizing the look

### Base maps

Override the theme's default tiles with any key in `rs.BASEMAPS`, or offer several as a switcher:

```python
print("available base maps:", list(rs.BASEMAPS))
rs.render_edges(edges, theme="light", basemap="positron")

# a thumbnail base-layer switcher on the map (folium)
rs.render_edges(edges, theme="dark", basemaps=["dark_matter", "positron", "satellite"])
```

Any [xyzservices](https://xyzservices.readthedocs.io/) provider also works directly as `basemap=`
(install `pip install "roadstyle[basemaps]"`).

### Your own colour vocabulary

`color_by` + `colors` defines exactly what each category looks like, with nothing to register:

```python
rs.render_edges(
    edges, theme="dark",
    color_by="congestion",
    colors={"free": "#22c55e", "slow": "#f59e0b", "jam": "#ef4444"},
    legend=True,
)
```

For *reusable* palettes shared across projects there's a registry + JSON I/O
(`register_palette`, `save_palette`, `load_palette`) — see [Palettes](palettes.md).

> Notebook: **06 · Customizing the look**

---

## 6 · Large datasets (GPU / lonboard)

For very large edge sets, switch the backend to **lonboard** (deck.gl / WebGL). Same call, same
styling — it just renders on the GPU. lonboard is optional: `pip install "roadstyle[lonboard]"`.

```python
rs.render_edges(edges, backend="lonboard", theme="dark")
rs.render_edges(edges, backend="lonboard", color_by="length_m", cmap="magma", width_by=(1, 5))
```

Use **folium** for portable, self-contained HTML and rich interactions; **lonboard** when edge
counts get large enough that Leaflet feels heavy.

> Notebook: **07 · Large datasets (lonboard)**

---

## 7 · Loading data — every input roadstyle accepts

`render_edges` / `to_spec` don't only take a `GeoDataFrame`. Everything funnels through `as_edges`,
which normalises **any** of the sources below to the one canonical shape (EPSG:4326 line geometry +
a class column). Hand roadstyle whatever you already have:

```python
rs.render_edges(gdf)                 # a GeoDataFrame
rs.render_edges("roads.gpkg")        # a file path: GeoPackage / GeoJSON / Shapefile / …
rs.render_edges(feature_collection)  # a GeoJSON mapping, a to_spec() dict, or __geo_interface__
rs.render_edges(arrow_table)         # a pyarrow Table (GeoArrow works directly)
```

For a plain WKB/WKT geometry column, or to set the source CRS, use the matching `from_*` helper and
pass its result on:

```python
# pyarrow with a WKB column
table = pa.table({
    "highway": edges["highway"].astype(str).tolist(),
    "geometry": [g.wkb for g in edges.geometry],
})
rs.render_edges(rs.from_arrow(table, geometry="geometry", crs=4326))

# DuckDB — select geometry as WKB (ST_AsWKB) or WKT (ST_AsText) so it round-trips.
# DuckDB carries no CRS, so crs= says what the coordinates are in.
e = rs.from_duckdb(con, "SELECT highway, aadt, ST_AsWKB(geom) AS geom FROM roads",
                   geometry="geom", crs=3006)
rs.render_edges(e, color_by="aadt", cmap="YlOrRd")
```

| You have… | Just pass it | For options use |
|---|---|---|
| GeoDataFrame / `RoadEdges` | `render_edges(gdf)` | `normalize_edges` |
| a file | `render_edges("roads.gpkg")` | `load_edges` |
| GeoJSON / spec | `render_edges(fc)` | `from_geojson` |
| pyarrow Table | `render_edges(table)` | `from_arrow` |
| DuckDB | — | `from_duckdb` |

Install the optional extras as needed: `pip install "roadstyle[duckdb,arrow]"`.

> Notebook: **08 · Loading data**

---

## 8 · Outputs for the web

The same styled map can leave roadstyle in several shapes. The heart of it is the **canonical JSON
spec** (`spec/1`): your data plus the *baked-in* per-edge style, ready for any frontend to draw.

```python
spec = rs.to_spec(edges, theme="dark", color_by="highway")   # canonical JSON dict
rs.save_spec(spec, "map_data.json")                          # round-trips with load_spec()

gj = rs.to_geojson(edges, color_by="highway")                # just the styled features

rs.save(edges, "standalone.html", theme="dark")              # a finished HTML file
html = rs.to_iframe(edges, theme="dark", height="360px")     # an <iframe> string, zero JS
```

Each feature in the spec carries reserved `__rs_*` properties (`__rs_fill`, `__rs_w`, `__rs_casing`,
…), so the browser never needs roadstyle's styling logic — it just reads them. See
[Embedding in a website](embedding.md) for the property contract and Leaflet / MapLibre snippets.

> Notebook: **04 · Outputs for the web**

---

## 9 · Embed in your own page (`roadstyle.js`)

The decoupled path: **Python computes the styling once** (a JSON spec), and the bundled, reusable
**`roadstyle.js`** draws it in the browser with your own UI on top. No Python at runtime, and you
don't write the renderer — it ships inside the package.

Copy the renderer next to your spec:

```python
import shutil
from importlib.resources import files

spec = rs.to_spec(edges, theme="dark", palette="highsat")
rs.save_spec(spec, "web/map_data.json")
for asset in ("roadstyle.js", "roadstyle.css"):
    shutil.copy(files("roadstyle") / "static" / asset, f"web/{asset}")
```

Then a minimal page wires it up. `RoadStyleMap` is headless — it exposes `getRoadClasses()`,
`setFilter()`, and selection events you react to:

```html
<link rel="stylesheet" href="./roadstyle.css"/>
<div id="map" style="height:100vh"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="./roadstyle.js"></script>
<script>
  // built-in widgets: legend, a road-type filter panel, and a base-layer switcher
  const m = new RoadStyleMap("map", { widgets: { legend: true, filter: true, basemap: true } });
  m.load("./map_data.json").then(() => {
    // build a filter UI from the classes present
    m.getRoadClasses().forEach(cls => { /* add a checkbox, then m.setFilter([...on]) */ });

    // react to clicks — feature.properties carries __rs_class + your original columns
    m.on("select",   f => console.log("selected", f.properties));
    m.on("deselect", () => console.log("cleared"));
  });
</script>
```

!!! warning "`file://` and `fetch()`"
    Browsers block `fetch()` from `file://`, so loading `map_data.json` by URL only works when the
    folder is *served* (`python -m http.server`). To make a page that opens with a double-click,
    inline the spec instead — `load()` takes a URL **or** an object. Notebook 05 shows the inlined
    pattern end to end.

Selection is **single**: clicking another road replaces it; click the same road again, or the map
background, to deselect. Full callback details are in
[Embedding → Reacting to a selection](embedding.md#reacting-to-a-selection-click-your-code).

> Notebook: **05 · Embedding with `roadstyle.js`**

---

## Where to next

- **[Parameter reference](parameters.md)** — every parameter of `render_edges` / `to_spec`.
- **[Embedding in a website](embedding.md)** — the JSON spec contract + Leaflet / MapLibre / iframe.
- **[Frontend integration](frontend.md)** — choosing baked HTML vs a JSON API vs `roadstyle.js`.
- **[Examples](examples.md)** — the runnable notebooks behind every section above.
