# Your first map with the Rust engine

<p class="lead">In this tutorial, we draw the roads of Monaco with the Rust engine, and we see that the page keeps them in vector tiles.</p>

You need Python 3.10 or newer and a connection to the internet (osmnx gets the roads from OpenStreetMap).

## Install roadstyle and osmnx

```bash
pip install roadstyle osmnx
```

The roadstyle wheel has the Rust engine in it. You do not need a Rust toolchain.

## Get the roads of Monaco

Make a file `monaco.py` with this code:

```python
import osmnx as ox
import roadstyle as rs

G = ox.graph_from_place("Monaco", network_type="drive", simplify=False)
G = ox.simplify_graph(G, edge_attrs_differ=["bridge", "tunnel"])
edges = ox.graph_to_gdfs(G, nodes=False)
print(len(edges), "edges")
```

Run it with `python monaco.py`. It prints the number of edges, for example `849 edges`. The number changes when OpenStreetMap changes.

## Draw the map with the Rust engine

Add these lines to the file:

```python
m = rs.render_edges(edges, name="Monaco")
m.save("monaco_rust.html")
```

Run the file again. It writes `monaco_rust.html`. Open it in a browser. You see the roads of Monaco on a base map. Move the mouse over a road, and the road glows. Click a road, and a popup shows its name and its class.

## The roads are in vector tiles

The page that you made keeps the roads as vector tiles (an embedded PMTiles archive). Tiles are the default. The file has all the tiles in it, but MapLibre decodes only the tiles in view. A large network opens fast.

To compare, add these lines. They write the roads as GeoJSON in place of tiles:

```python
g = rs.render_edges(edges, name="Monaco", tiles=False)
g.save("monaco_geojson.html")
```

Run the file and open `monaco_geojson.html`. The map looks the same as `monaco_rust.html`. The two files have nearly the same size. On a large network, MapLibre draws the tiled page with fewer triangles, so its pan and zoom are faster. For the other ways to send tiles to the browser, see [Make tiles and PMTiles](tiles.md).

## What we did

We drew a map with the Rust engine. Its roads are vector tiles by default. `tiles=False` gives GeoJSON roads. Next:

- [Use roadstyle in the browser](browser.md): the same engine with no Python.
