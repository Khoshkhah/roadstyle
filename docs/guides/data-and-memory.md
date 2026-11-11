# How a dashboard holds its data

<p class="lead">A dashboard shows several types of data: road lines, other map layers, 3D objects, the ground, tables, and values that
change with time. This page tells how each type gets into the browser, in each of the three ways to run a dashboard.</p>

## The rule

A page keeps only the data that is in view, and in the time window of a run. The memory of a page must not grow with the size of the
area, the number of layers, or the length of a run.

To obey this rule, roadstyle cuts each type of data in one of two ways:

- **By place:** the data is cut into tiles. The map loads the tiles in view and frees the tiles that go out of view.
- **By time:** the values of a run are cut into frames. The page keeps a window of frames around the frame that it shows.

## The three ways to run a dashboard

| Way | Where the data is | Use it for | How to make it |
|---|---|---|---|
| **A. One HTML file** | In the file | A small area. A file to send, or to open from the disk. | `rs.render_edges(...)`, `rs.render_dashboard(...)` |
| **B. Files on a server** | In files at a URL. The browser reads only the parts that it needs (HTTP range requests). | A large area. A website or another map app. | `rs.export_style(...)` with a PMTiles file |
| **C. Made in the browser** | The page makes the data from its input files. It keeps the result in memory or on the browser disk (OPFS). | A page that builds its maps itself, for example duckOSM Studio. | roadstyle-wasm: `new LiveMap(...)`, `new Tiler(...)` |

The file formats are the same in the three ways: PMTiles for the tiles, and Parquet for the tables. Only the transport changes. A static file
host is enough for way B, and no running server is necessary. [Make tiles and PMTiles](../rust/tiles.md) tells how to make the files.

## The types of data

| Type of data | How it is cut | A. One HTML file | B. Files on a server | C. Made in the browser |
|---|---|---|---|---|
| [Road lines](#road-lines-and-other-layers) | Tiles | Tiles in the file | Tiles from the PMTiles file | The map worker makes a tile when the map asks for it |
| [Other layers](#road-lines-and-other-layers) (water, land, buildings, boundary) | Tiles | GeoJSON in the file (planned: tiles) | Tiles | Tiles from the map worker |
| [3D objects](#3d-objects) (walls, bridge decks, piers) | Pieces by tile | All objects at one time (planned: by tile) | Planned: by tile | Walls: tiles from the map worker. Decks: all at one time (planned: by tile). |
| [The ground](#the-ground) | Tiles of one terrain file | The terrain file at a URL | Tiles from the terrain file | A terrain file on the browser disk |
| [Tables](#tables-in-memory-or-on-the-disk) (road fields, popups, queries) | Rows, read by query | The road table in the page | The host reads Parquet at a URL | The host keeps each table in memory or on the browser disk |
| [Values in time](#values-in-time) | Frames | One table of values at a time | One table of values at a time | One table of values at a time (planned: a window of frames) |
| [Moving points](#moving-points) (vehicles) | Frames | Planned | Planned | Planned |

"Planned" means that the design is in the repository ([memory_budget.md](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/memory_budget.md)),
but the code is not on `main`.

## How the map puts the layers together

Each type of data is a separate source, and each source has its own layers. The style puts all the layers in one order, from the bottom to
the top. MapLibre draws the tiles of each source in view, layer on layer.

- **The flat layers** (the base map, the other layers and the roads) lie on the ground. The roads come in their level order, so a bridge
  is on top of the road under it ([Which road is on top](levels.md)).
- **The 3D objects** stand on the flat layers.
- **A new type of data** adds one source and its place in the order. It does not change the other sources.

Each source loads its tiles when the map asks for them. A source that is hidden loads nothing.

## Road lines and other layers

A road line in a tile has its geometry, its id, and only the keys that the style reads. Its other fields are in the [tables](#tables-in-memory-or-on-the-disk).
The three ways give the same tiles ([Big networks](big-networks.md)):

- **A:** the tiles are in the HTML file.
- **B:** the browser reads each tile from the PMTiles file with a range request.
- **C:** the map worker keeps the roads and cuts a tile only when the map asks for it.

The other layers follow the same rule. In way A, they are GeoJSON in the file today. Then the whole layer stays in memory.

## 3D objects

A 3D object is cut into pieces by tile, the same as a line. The map loads the pieces of the tiles in view.

**Load a layer only when it shows.** A host can give roadstyle a function, not the data. roadstyle calls the function one time, when
the layer first shows. Until then, the page has no data for that layer. `rsSetWalls` works this way ([JavaScript API](../reference/javascript.md)).

## The ground

The ground of an area (the hillshade and the 3D terrain) comes from one terrain file: PMTiles with the heights as tiles. The page reads one
tile at a time:

- **A and B:** the terrain file at a URL.
- **C:** a `File` on the browser disk (OPFS), or the bytes in memory.

The page gives the file with the page option `ground`, or with `rsGround(ground)` ([JavaScript API](../reference/javascript.md)).
Without a ground, the map uses the AWS Terrain Tiles.

## Tables: in memory or on the disk

A table holds the fields of each road or object, for the popups, the filters and the [data dock](data-dock.md). roadstyle does not
hold the large tables. The host page keeps them in DuckDB-wasm, and gives roadstyle small functions: one row for a popup, or the result
of a query.

The host gives each table a home:

| Home | What it is | Speed | Memory |
|---|---|---|---|
| `memory` | A DuckDB table, made from the Parquet file | The fastest queries | All the rows |
| `disk` | A DuckDB view over the Parquet file on the browser disk (OPFS) | DuckDB reads only the parts that a query needs | Almost none |
| `auto` | A small file goes to `memory`, a large file goes to `disk` | | |

A table can move between the two homes, because the Parquet file stays on the disk:

- **To load a table into memory:** make a DuckDB table from the file.
- **To unload it:** drop the table and make the view over the file again. No data is lost.

duckOSM Studio is an example. Its address sets the rule: `?tables=memory`, `?tables=disk` or `?tables=auto` (the default). With `auto`,
a file larger than 256 KiB goes to the disk.

In way B, the host reads the Parquet files at a URL. DuckDB-wasm reads only the row groups that a query needs. In way A, the page has
its road table in memory.

## Values in time

Values in time are the data of a run: for example, the flow on each road at each second of a simulation.

**Now:** `rs.setData(rows, options)` colours the roads from one table of values. A second call replaces the values
([JavaScript: live data](dashboard-manual/javascript.md#live-data-a-new-day)). A page that plays a run calls it for each step.

**Planned:** roadstyle keeps a window of frames, and the host gives the frames:

```js
rs.setFrames({
  frames: (from, to) => host.loadFrames(from, to),  // a Promise of [{t, values: Float32Array}]: one value for each road
  count: 3600,                                      // the number of frames in the run
  window: 60,                                       // the frames that stay in memory
});
rs.showFrame(i);                                    // show frame i; roadstyle loads the window around it
```

The host decides where the frames come from: Parquet on the browser disk or at a URL, or a running simulation. A frame is one number for
each road, so 100,000 roads use 400 KB for each frame. A window of 60 frames uses 24 MB, for a run of any length.

## Moving points

**Planned.** Moving points (for example, vehicles) follow the same window rule as the values in time. Each frame has the position, the
direction and a value of each point. The page draws only the points in view.
