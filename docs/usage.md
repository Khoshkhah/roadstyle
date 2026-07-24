# Usage

## Install

```bash
pip install git+https://github.com/Khoshkhah/roadstyle.git
```

Optional extras pull in heavier backends/inputs only when you ask for them:

```bash
pip install "roadstyle[lonboard] @ git+https://github.com/Khoshkhah/roadstyle.git"   # WebGL backend
# numeric  — continuous data-driven styling (mapclassify + matplotlib colormaps)
# basemaps — any xyzservices tile provider as a base map
# duckdb / arrow — read edges straight from a DuckDB query or an Arrow table
```

**Develop locally** (editable, from the repo root — a src layout): `pip install -e ".[dev]"`, or with
conda `conda env create -f environment.yml && conda activate roadstyle && pip install -e ".[dev]"`.

## Command line

No Python needed — `roadstyle` renders any road file straight from the shell:

```bash
roadstyle edges.gpkg -o map.html --basemap dark_matter               # styled interactive map
roadstyle edges.gpkg --include motorway trunk primary       # keep only major roads
roadstyle edges.gpkg --color-by aadt --cmap viridis --width-by 1 6   # colour by your data
roadstyle edges.gpkg -f spec -o map_data.json               # JSON spec for your own frontend

roadstyle studio                                            # the interactive Streamlit workbench
roadstyle studio --server.port 8502                         # extra args are forwarded to streamlit
```

`-f/--format` is one of `web` (self-contained MapLibre map, **default**), `folium`, `rsjs`
(roadstyle.js page), `spec`, `geojson`; every other flag mirrors a `render_edges` keyword (the
`web` map also takes `--no-arrows`/`--no-labels`/`--no-filter`/`--no-basemap-switcher`). See
`roadstyle --help`. `roadstyle studio` (from the `studio` extra) launches the
[workbench](studio.md) and forwards any extra arguments to `streamlit run`.

## Input — what roadstyle expects

roadstyle styles **road edges**: a `GeoDataFrame` (or a `RoadEdges`) with **line geometry**
(LineString/MultiLineString) and at least one column to style by. You load your data however you
like; roadstyle normalises it (reproject to EPSG:4326, drop non-line rows, optionally rename your
class column):

```python
import geopandas as gpd
import roadstyle as rs

raw = gpd.read_file("edges.gpkg")              # GeoPackage / GeoJSON / Shapefile / PostGIS / …
edges = rs.normalize_edges(raw, class_col="highway", rename={"vagtyp": "highway"})
```

`render_edges` (and `to_spec`, etc.) also accept a plain GeoDataFrame and normalise it for you.
Roads already in **DuckDB**? `rs.from_duckdb(con, query)` renders straight from a SQL query
(select the geometry as WKB with `ST_AsWKB`) — see `examples/roads_from_duckdb.py`.

## Quick start

```python
edges = gpd.read_file("edges.gpkg")            # needs a `highway` column
rs.render_edges(edges, basemap="dark_matter").save("roads.html")
```

`render_edges` returns a `WebMap` by default (the MapLibre `web` backend), or a `folium.Map` with
`backend="folium"`, or a `lonboard.Map` with `backend="lonboard"` — so you can keep customising it,
`.save()` it, or display it inline in a notebook.

## Recipes

```python
# Palettes, base maps, filtering, selection
rs.render_edges(edges, palette="carto",
                include=["motorway", "trunk", "primary"])
rs.render_edges(edges, basemap="satellite")
rs.render_edges(edges, selected=picked_edges)          # neon-violet highlight

# Data-driven: categorical (e.g. congestion levels)
rs.render_edges(edges, color_by="congestion",
                colors={"low": "#11D68F", "moderate": "#FFCF43",
                        "heavy": "#F24E42", "severe": "#A92727"}, legend=True)

# Data-driven: numeric (e.g. traffic volume) with a width ramp + gradient legend
rs.render_edges(edges, color_by="aadt", cmap="viridis",
                vmin=0, vmax=20000, width_by=(1, 8), legend=True)

# Per-edge colour from your own edge_id -> colour table (gray fallback for misses)
rs.render_edges(edges, color_table={"4897…": "#e6194B", "5193…": "#3cb44b"})
rs.render_edges(edges, color_by="color", colors="self")   # colour already a column

# GPU backend for very large edge sets
rs.render_edges(big_edges, backend="lonboard", color_by="aadt", cmap="magma")

# self-contained MapLibre map (per-zoom widths, two-way lanes, arrows, names,
# hover/select, base switcher, tunnel/bridge grade separation) — opens offline, no server
rs.render_edges(edges, backend="web", basemap="dark_matter").save("roads.html")
```

## MapLibre web backend

`backend="web"` renders a finished, **zoom-correct** MapLibre vector map as one **self-contained**
HTML file (MapLibre + data bundled in — opens from disk with no server, no internet). It adds
two-way directional lanes, direction arrows, curved street names, hover/select, a base-layer
switcher, and **tunnel/bridge grade separation** (reads optional `tunnel`/`bridge`/`layer`
columns). It returns a `WebMap` with `.save(path)`.

```python
rs.render_edges(edges, backend="web", basemap="dark_matter",
                offset_frac=0.28, width_frac=0.6, offset_zoom=15).save("roads.html")
```

Toggle the UI with `arrows` / `labels` / `filter_control` / `basemap_switcher` (all default `True`).
See **[MapLibre web backend](web-backend.md)** for the full feature list and parameters. (This is
distinct from `rs.save` / `-f rsjs`, which writes the roadstyle.js *spec page* for embedding.)

```python
# Switchable data-driven colouring: a neutral mono base + a "Colour by" dropdown that
# recolours client-side (no re-render). Blank edges keep the base colour, not a flat grey.
rs.render_edges(edges, backend="web", palette="mono",
    color_options={"Class": {}, "AADT": {"color_by": "aadt", "cmap": "viridis"},
                   "Speed": {"color_by": "speed_kph", "cmap": "magma"}}).save("recolor.html")

# Extra overlay layers you bring (zones / POIs / any geometry): drawn under/over the roads,
# clickable, toggled from a Layers control.
rs.render_edges(edges, backend="web",
    overlays=[rs.Overlay(zones, kind="fill", placement="under", color="#6aa9ff",
                         opacity=0.14, label="Zones", popup=["taz_id", "weight"]),
              rs.Overlay(pois, kind="circle", placement="over", color="#ff5d5d",
                         radius=7, label="POIs", popup=["name", "type"])]).save("overlays.html")
```

Prefer to **see** these working? The **[Manual](manual.md)** walks through them with the live map
embedded after each step.

## Settings & the JavaScript API

Every styling default lives in one settings file with a 5-level override ladder — see
[Palettes → settings](palettes.md#customising-data-files-and-overrides); per-call:
`render_edges(edges, settings={...})`. And every in-map control is scriptable from JS
(`rsSetBasemap`, `rsQuery` id-set verbs, `rs:*` events) — see
[the JS API](web-backend.md#the-javascript-api-windowrs) and the copyable
[`ui/` templates](https://github.com/Khoshkhah/roadstyle/tree/main/ui).

## Custom (non-OSM) road classes

```python
from roadstyle import register_palette, RoadStyle, color_by_class
register_palette("nvdb", {"0": RoadStyle("#00E5FF", 6, 8),
                          "1": RoadStyle("#FF9100", 4.5, 6.5)})
rs.render_edges(edges, style=color_by_class("functional_road_class",
                                            palette="nvdb", normalize_links=False))
```

Palettes can also be saved/loaded as JSON (`save_palette` / `load_palette`) so a non-coder can
edit colours, or a web frontend can share the same colour source.

## Web output

```python
spec = rs.to_spec(edges, color_by="aadt", cmap="viridis")  # canonical JSON dict
rs.save_spec(edges, "roads.json", color_by="aadt", cmap="viridis")
rs.save(edges, "roads.html", color_by="aadt", cmap="viridis")   # standalone HTML
html = rs.to_iframe(edges, color_by="aadt", cmap="viridis")     # <iframe> string
```

See **[Embedding in a website](embedding.md)** for the JSON spec and frontend snippets, and the
**[Parameter reference](parameters.md)** for every parameter.

## Input formats (what `render_edges` / `to_spec` accept)

Everything funnels through `as_edges`, so the entry points take more than a GeoDataFrame — pass
whichever you already have and roadstyle normalises it (to EPSG:4326 line geometry):

```python
import roadstyle as rs

rs.render_edges(gdf)                       # a GeoDataFrame
rs.render_edges("roads.gpkg")             # a file path (GeoPackage / GeoJSON / Shapefile / …)
rs.render_edges(feature_collection)        # a GeoJSON mapping / a to_spec() dict / __geo_interface__
rs.render_edges(arrow_table)               # a pyarrow Table
```

For **DuckDB** (and to control the geometry column / source CRS), use the matching helper and pass
its result on — select the geometry as WKB or WKT so it round-trips:

```python
edges = rs.from_duckdb(
    con,
    "SELECT highway, aadt, ST_AsWKB(geom) AS geom FROM roads",
    geometry="geom", crs=3006,             # DuckDB carries no CRS; say what the coords are in
)
rs.render_edges(edges, color_by="aadt", cmap="YlOrRd")
```

`from_geojson` / `from_arrow` / `from_duckdb` / `load_edges` all return a `RoadEdges`; install the
optional `duckdb` / `arrow` extras (`pip install roadstyle[duckdb,arrow]`) as needed.
