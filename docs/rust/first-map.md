# Your first map with the Rust engine

<p class="lead">In this tutorial, we draw the roads of Monaco with the Rust engine and put them in vector tiles.</p>

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

Run it with `python monaco.py`. It writes the number of edges, for example `849 edges`. The number changes when
OpenStreetMap changes.

## Draw the map with the Rust engine

Add these lines to the file:

```python
m = rs.render_edges(edges, name="Monaco")
m.save("monaco_rust.html")
```

Run the file again. It writes `monaco_rust.html`. Open it in a browser. You see the roads of Monaco on a base map, with
bridges over tunnels. Move the mouse over a road: the road glows. Click a road: a popup shows its name and its class.

!!! note "A warning about CARTO"
    The default base map is CARTO Voyager. Without a CARTO key, Python writes a warning and the base-map tiles show
    "API KEY REQUIRED". The roads are not affected. To use a base map with no key, add `basemap="osm"`, or read
    [Base maps and API keys](../reference/settings.md#base-maps-api-keys).

## Put the roads in vector tiles

For a large network, the page can keep the roads as vector tiles (an embedded PMTiles archive). Add these lines:

```python
t = rs.render_edges(edges, name="Monaco", tiles=True)
t.save("monaco_tiles.html")
```

Run the file and open `monaco_tiles.html`. The map looks the same as `monaco_rust.html`. The file has all the tiles in it, but
MapLibre decodes only the tiles that it shows, so a large network opens fast. The other ways to get tiles to the browser are in
[Make tiles and PMTiles](tiles.md).

## What we did

We drew a map with the Rust engine and put its roads in vector tiles. Next:

- [Use roadstyle in the browser](browser.md): the same engine with no Python.
