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
roadstyle edges.gpkg -o map.html --theme dark               # styled interactive map
roadstyle edges.gpkg --include motorway trunk primary       # keep only major roads
roadstyle edges.gpkg --color-by aadt --cmap viridis --width-by 1 6   # colour by your data
roadstyle edges.gpkg -f spec -o map_data.json               # JSON spec for your own frontend
```

`-f/--format` is one of `folium` (default), `web`, `spec`, `geojson`; every other flag mirrors a
`render_edges` keyword. See `roadstyle --help`.

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

## Quick start

```python
edges = gpd.read_file("edges.gpkg")            # needs a `highway` column
rs.render_edges(edges, theme="dark").save("roads.html")
```

`render_edges` returns a `folium.Map` (or a `lonboard.Map` with `backend="lonboard"`), so you can
keep customising it, `.save()` it, or display it inline in a notebook.

## Recipes

```python
# Themes, palettes, filtering, satellite, selection
rs.render_edges(edges, palette="carto", theme="light",
                include=["motorway", "trunk", "primary"])
rs.render_edges(edges, theme="satellite", basemap="satellite")
rs.render_edges(edges, selected=picked_edges)          # neon-violet highlight

# Data-driven: categorical (e.g. congestion levels)
rs.render_edges(edges, color_by="congestion",
                colors={"low": "#11D68F", "moderate": "#FFCF43",
                        "heavy": "#F24E42", "severe": "#A92727"}, legend=True)

# Data-driven: numeric (e.g. traffic volume) with a width ramp + gradient legend
rs.render_edges(edges, color_by="aadt", cmap="viridis",
                vmin=0, vmax=20000, width_by=(1, 8), legend=True)

# GPU backend for very large edge sets
rs.render_edges(big_edges, backend="lonboard", color_by="aadt", cmap="magma")
```

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
