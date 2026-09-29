# Roads from OpenStreetMap

<p class="lead">No road data of your own? Download any place from OpenStreetMap with osmnx and draw it in four lines.</p>

[osmnx](https://osmnx.readthedocs.io/) downloads the road network of any area from OpenStreetMap.
roadstyle takes its edges as they are (roadstyle 0.9 and later).

```python
import osmnx as ox                       # pip install osmnx
import roadstyle as rs

G = ox.graph_from_place("Tartu, Estonia", network_type="drive", simplify=False)
G = ox.simplify_graph(G, edge_attrs_differ=["bridge", "tunnel"])
rs.render_edges(ox.graph_to_gdfs(G, nodes=False)).save("tartu.html")
```

Why the second line is there: see [bridges and tunnels](#bridges-and-tunnels) below.

## Choose the area

Every osmnx download starts from an area. Pick the call that matches what you have:

| You have | Call |
|---|---|
| a place name | `ox.graph_from_place("Södermalm, Stockholm", ...)` |
| a point and a distance | `ox.graph_from_point((59.315, 18.07), dist=1000, ...)`: `(lat, lon)`, metres |
| a bounding box | `ox.graph_from_bbox((west, south, east, north), ...)` |
| a polygon | `ox.graph_from_polygon(polygon, ...)`: shapely, in EPSG:4326 |

Add `simplify=False` to each, then simplify as in the example above. A district takes a minute or two
to download (Södermalm: about 90 seconds); a county or a whole country can take much longer.

## Choose the roads

`network_type` picks which ways are downloaded. Always pass it: osmnx's default is `"all"`.

| `network_type` | Roads |
|---|---|
| `"drive"` | public roads for cars |
| `"drive_service"` | the same, plus service roads (driveways, parking aisles) |
| `"walk"` | everything a pedestrian can use, including footways and steps |
| `"bike"` | everything a cyclist can use |
| `"all"` / `"all_public"` | every way / every public way |

roadstyle styles each edge by its `highway` class, so footways and cycleways get their own look.

## Two things about osmnx data

### The graph is directed

A two-way street is two edges, one per direction, and a one-way street is one. That is exactly
what roadstyle expects: it draws the two directions side by side and puts arrows on one-way
streets. Keep the graph directed; don't convert it with `ox.convert.to_undirected`.

### Bridges and tunnels

By default osmnx joins consecutive OpenStreetMap ways into one edge wherever no junction separates
them. A tunnel that runs straight onto a bridge becomes one edge tagged both `tunnel` and `bridge`,
and roadstyle draws the whole of it as a bridge. In Stockholm, Söderledstunneln and Centralbron
became a single 1.5 km edge this way.

The fix is to download without simplifying, then simplify yourself without merging across the start
or end of a bridge or tunnel:

```python
G = ox.graph_from_place(place, network_type="drive", simplify=False)
G = ox.simplify_graph(G, edge_attrs_differ=["bridge", "tunnel"])
```

It costs a few percent more edges (1,470 instead of 1,361 for Södermalm). If you forget, roadstyle
warns: *"6 edges are tagged both bridge and tunnel and will be drawn as bridges"*.

The merged edges also hold lists, such as `name = ['Götgatan', 'Ringvägen']`. roadstyle keeps the
first value of each list, and turns osmnx's `(u, v, key)` index into ordinary columns.

## Style by any OSM tag

osmnx keeps the OpenStreetMap tags as columns (`name`, `maxspeed`, `lanes`, `oneway`, …), so
everything in [Colour by your data](colour.md) works on them. `maxspeed` is text in OSM (`"30"`,
sometimes `"SE:urban"`), so make it a number first:

```python
import pandas as pd

edges = ox.graph_to_gdfs(G, nodes=False)
edges["speed_kmh"] = pd.to_numeric(edges["maxspeed"], errors="coerce")
rs.render_edges(edges, color_by="speed_kmh", cmap="plasma", legend=True).save("speed.html")
```

## When the download fails

osmnx caches every download in a `cache/` folder next to where you run it, so an area is only
downloaded once. Delete the folder to fetch fresh data.

The downloads come from the public Overpass servers, which are sometimes busy or down. osmnx then
fails with `Connection refused` or a timeout. Wait and retry, or point osmnx at another server:

```python
ox.settings.overpass_url = "https://maps.mail.ru/osm/tools/overpass/api"
```

This is the osmnx 2.x setting. Older tutorials show `ox.settings.overpass_endpoint`, which osmnx
2.x no longer reads: setting it changes nothing. A different server also means a different cache
entry, so the area is downloaded again.

## The notebook

[notebooks/10_osmnx.ipynb](https://github.com/Khoshkhah/roadstyle/blob/main/notebooks/10_osmnx.ipynb)
walks through all of this on Södermalm, with the maps.

AI agents can do the same without code: the MCP server's `render_place` tool downloads and draws a
place in one call. See [AI agents](agents.md).
