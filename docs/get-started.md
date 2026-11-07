# Get started

<p class="lead">Install roadstyle, draw your first map, and learn what your data needs.</p>

## Install

You need Python 3.10 or newer.

```bash
pip install roadstyle
pip install "roadstyle[duckdb,arrow]"   # extras combine; "roadstyle[all]" gives every extra
```

| Extra | What it adds |
|---|---|
| `duckdb` | `rs.from_duckdb`: edges from a DuckDB query |
| `arrow` | `rs.from_arrow`: edges from a pyarrow Table |
| `basemaps` | each tile provider of xyzservices as a base map |
| `studio` | `roadstyle studio`: maps with no code |
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

    An install from the source (a clone or git) builds roadstyle's Rust engine with maturin, so it needs a Rust
    toolchain ([rustup](https://rustup.rs)). The wheels on PyPI have the engine in them. To work on the engine without an install,
    use `PYTHONPATH=src` and build the module with `python rust/roadstyle-py/build.py`.

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

The file has all its data in it, so it opens from disk with no server. Move the pointer over a road to light it, and click
a road to see its fields. The button **Base map and layers** in the map's controls changes the base map. In a notebook the map shows in the cell. The
notebook needs the network, because the map loads MapLibre from a CDN.

!!! note "Street View needs a server"
    The Street View window works only on a page that a server gives (http or https), for example `python -m http.server`.
    It does not work in a page that you open as a file.

## What your data needs

| Column | Necessary? | What it gives |
|---|---|---|
| `geometry` | yes | LineString or MultiLineString, in any CRS (roadstyle changes it to WGS 84) |
| `highway` | yes | the road class (the OSM values); for another column name, use `highway_col=` |
| `name` | no | the street names, and the title of the popup |
| `oneway` | no | the one-way arrows |
| `bridge`, `tunnel`, `layer` | no | which road is on top: a tunnel under, a bridge over |
| `edge_id` | no | an id that stays correct also above 2\*\*53 |
| other columns | no | the popup shows them, and JavaScript can read them |

An edge has a **direction**: its line goes the way the traffic goes. A two-way road is two edges, one in each direction. Do not
join them: roadstyle draws them as two lanes in one outline. A two-way footway, path, steps or cycleway is one line.

## Load your data

`render_edges` takes a GeoDataFrame, a file path, a GeoJSON mapping, a pyarrow Table or the edges of osmnx.

=== "A file"

    ```python
    rs.render_edges("roads.gpkg")          # GeoPackage, GeoJSON, Shapefile, GeoParquet
    ```

=== "OpenStreetMap"

    ```python
    import osmnx as ox                     # pip install osmnx
    G = ox.graph_from_place("Tartu, Estonia", network_type="drive", simplify=False)
    G = ox.simplify_graph(G, edge_attrs_differ=["bridge", "tunnel"])   # keep a tunnel apart from its bridge
    rs.render_edges(ox.graph_to_gdfs(G, nodes=False))
    ```

    More in [Roads from OpenStreetMap](guides/osmnx.md).

=== "DuckDB"

    ```python
    import duckdb                          # the extra duckdb
    con = duckdb.connect("roads.duckdb")
    con.sql("INSTALL spatial; LOAD spatial")
    e = rs.from_duckdb(con, "SELECT highway, name, ST_AsWKB(geom) AS geom FROM edges",
                       geometry="geom", crs=4326)   # DuckDB keeps no CRS: give it
    rs.render_edges(e).save("roads.html")
    ```

=== "pyarrow"

    ```python
    import pyarrow as pa                   # the extra arrow
    table = pa.table({"highway": edges["highway"].astype(str).tolist(),
                      "geometry": [g.wkb for g in edges.geometry]})
    rs.render_edges(rs.from_arrow(table, geometry="geometry", crs=edges.crs))
    ```

## Next steps

- [Style the roads](guides/style.md): palettes, base maps, names, 3D bridges.
- [Colour by your data](guides/colour.md): the colours and a legend from a column.
- [Street View](guides/street-view.md): the window, or a page with Street View beside the map.
- [Dashboards](guides/dashboards.md): a map with a toolbox and a panel, from one Python call.
- [Every parameter](reference/parameters.md) and the [command line](reference/cli.md).
