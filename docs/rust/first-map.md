# Your first map with the Rust engine

<p class="lead">In this tutorial, we draw the roads of Monaco with the Rust engine. Then we compare the page with the page of the
Python engine, and we measure the two engines.</p>

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
m = rs.render_edges(edges, name="Monaco", engine="rust")
m.save("monaco_rust.html")
```

Run the file again. It writes `monaco_rust.html`. Open it in a browser. You see the roads of Monaco on a base map, with
bridges over tunnels. Move the mouse over a road: the road glows. Click a road: a popup shows its name and its class.

!!! note "A warning about CARTO"
    The default base map is CARTO Voyager. Without a CARTO key, Python writes a warning and the base-map tiles show
    "API KEY REQUIRED". The roads are not affected. To use a base map with no key, add `basemap="osm"`, or read
    [Base maps and API keys](../reference/settings.md#base-maps-api-keys).

## Compare with the Python engine

Add these lines:

```python
p = rs.render_edges(edges, name="Monaco")      # the default engine: Python
print("same page:", m.html == p.html)
```

Run the file. It writes `same page: True`. The two engines write the same page, byte for byte.

## Measure the two engines

Add these lines:

```python
import time

for engine in ("python", "rust"):
    t = time.perf_counter()
    rs.render_edges(edges, name="Monaco", engine=engine)
    print(engine, f"{time.perf_counter() - t:.1f} s")
```

Run the file. On the machine of [Parity and speed](parity.md) it writes this (the times change a little from run to run):

```text
python 0.9 s
rust 0.3 s
```

Monaco is small. The difference is larger on a large area: Tartu (64,828 roads) takes 19.1 s with Python and 6.2 s with Rust.

## Put the roads in vector tiles

For a large network, the page can keep the roads as vector tiles (an embedded PMTiles archive). Add these lines:

```python
t = rs.render_edges(edges, name="Monaco", engine="rust", tiles=True)
t.save("monaco_tiles.html")
```

Run the file and open `monaco_tiles.html`. The map looks the same as `monaco_rust.html`. The file has all the tiles in it, but
MapLibre decodes only the tiles that it shows, so a large network opens fast. The other ways to get tiles to the browser are in
[Make tiles and PMTiles](tiles.md).

## What we did

We drew a map with the Rust engine, we saw that its page is the same as the page of the Python engine, and we measured the two
engines. Next:

- [Switch the engine](switch-engine.md) for a whole program, with `ROADSTYLE_ENGINE`.
- [Keywords by engine](keywords.md): what the Rust engine does and what stays in Python.
- [Use roadstyle in the browser](browser.md): the same engine with no Python.
