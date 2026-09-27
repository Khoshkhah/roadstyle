# Get started

<p class="lead">Install roadstyle, draw your first map, and learn what your data needs.</p>

## Install

Python 3.10 or newer.

```bash
pip install roadstyle
pip install "roadstyle[numeric,tiles]"   # extras combine; "roadstyle[all]" takes every one
```

| Extra | Enables |
|---|---|
| `numeric` | numeric colour ramps (`color_by` on numbers, `cmap`) |
| `tiles` | `tiles=True`, vector tiles inside the file for big networks |
| `lonboard` | the GPU backend for very large networks |
| `duckdb` | `rs.from_duckdb`, edges from a DuckDB query |
| `arrow` | edges from a pyarrow Table |
| `basemaps` | any xyzservices tile provider as a base map |
| `studio` | `roadstyle studio`, the no-code workbench |
| `all` | every extra above |

??? note "Developing roadstyle"

    ```bash
    git clone https://github.com/Khoshkhah/roadstyle.git && cd roadstyle
    pip install -e ".[dev]"     # every extra + pytest, ruff, mypy
    # or: conda env create -f environment.yml && conda activate roadstyle && pip install -e ".[dev]"
    pytest                      # browser tests need `pip install playwright`
    ```

    The latest unreleased version without a clone:
    `pip install "roadstyle[all] @ git+https://github.com/Khoshkhah/roadstyle.git"`.

## Your first map

<iframe src="../maps/first_map.html" loading="lazy" title="A first roadstyle map of Södermalm" class="rs-demo"></iframe>

=== "Python"

    ```python
    import geopandas as gpd
    import roadstyle as rs

    edges = gpd.read_file("sodermalm_edges.gpkg")
    m = rs.render_edges(edges)
    m.save("first_map.html")     # m.html is the page as a string
    ```

=== "Command line"

    ```bash
    roadstyle sodermalm_edges.gpkg -o first_map.html
    ```

The file is self-contained: it opens from disk with no server. Hover a road to highlight it, click
it for its attributes, and switch the base map with the button at the bottom right. In a notebook
the map shows inline.

!!! note "Street View needs a server"
    The Street View button works only when the page is served over http(s), for example with
    `python -m http.server`, not when it is opened as a file.

## What your data needs

| Column | Needed? | Switches on |
|---|---|---|
| `geometry` | required | LineString or MultiLineString, any CRS (reprojected for you) |
| `highway` | required | the road class (OSM values); another name: `highway_col=` |
| `name` | optional | street labels, the popup title |
| `oneway` | optional | one-way arrows |
| `bridge`, `tunnel`, `layer` | optional | grade separation: tunnels under, bridges on top |
| `edge_id` | optional | an id kept exact even past 2\*\*53 |
| anything else | optional | shown in the popup, queryable from JavaScript |

An edge is **directed**: its geometry runs the way traffic flows. A two-way road is two edges with
reversed geometry, drawn side by side, so do not merge them.

## Loading data

`render_edges` takes a GeoDataFrame, a file path, a GeoJSON mapping or a pyarrow Table. For a WKB
geometry column or a DuckDB query, use a helper:

```python
rs.render_edges("roads.gpkg")                            # GeoPackage, GeoJSON, Shapefile, ...

import duckdb                                            # needs the duckdb extra
con = duckdb.connect("roads.duckdb")
con.sql("INSTALL spatial; LOAD spatial")
e = rs.from_duckdb(con, "SELECT highway, name, ST_AsWKB(geom) AS geom FROM edges",
                   geometry="geom", crs=4326)            # DuckDB has no CRS: say what it is
rs.render_edges(e).save("roads.html")

import pyarrow as pa                                     # needs the arrow extra
table = pa.table({"highway": edges["highway"].astype(str).tolist(),
                  "geometry": [g.wkb for g in edges.geometry]})
rs.render_edges(rs.from_arrow(table, geometry="geometry", crs=edges.crs))
```

## Next steps

- [Style the roads](guides/style.md): palettes, base maps, labels, 3D bridges.
- [Colour by your data](guides/colour.md): a column becomes colour and a legend.
- [Google Street View](guides/street-view.md): the window, or a page with Street View beside the map.
- [Dashboards & JavaScript](guides/dashboards.md): ready-made pages and the `rs*` API.
- [Every parameter](reference/parameters.md) and the [command line](reference/cli.md).
