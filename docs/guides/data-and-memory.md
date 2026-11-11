# How a dashboard holds its data

<p class="lead">A dashboard shows several types of data: road lines, other map layers, 3D objects, the ground, tables, and values that
change with time. This page tells how each type gets into the browser, in each of the four ways to run a dashboard.</p>

## The rule

A page keeps only the data that is in view, and in the time window of a run. The memory of a page must not grow with the size of the
area, the number of layers, or the length of a run.

To obey this rule, roadstyle cuts each type of data in one of two ways:

- **By place:** the data is cut into tiles. The map loads the tiles in view and frees the tiles that go out of view.
- **By time:** the values of a run are cut into frames. The page keeps a window of frames around the frame that it shows.

## Memory and storage in the browser

A page can keep its data in three places. They are different in speed, in size, and in how long the data stays.

| Place | What it is | Speed | Size | How long the data stays |
|---|---|---|---|---|
| **Memory** of the tab | The working memory of the page: its JavaScript objects, its workers (the map worker, DuckDB-wasm) and their WebAssembly memory | The fastest | Limited. A WebAssembly module can use at most 4 GB. When a tab uses too much memory, the browser stops the tab. | Until the tab closes or reloads |
| **Browser disk** (OPFS) | The Origin Private File System: files on the computer's disk that only pages of the same site can open. The person does not see them in a folder. | Fast. A page reads only the part of a file that it needs (`File.slice`, or a sync access handle in a worker). | A part of the free disk space. The browser sets the quota; `navigator.storage.estimate()` gives the use and the quota. | After a reload and a restart, until the page removes the files. The browser can clear them when the disk is full, unless the page asks for persistent storage (`navigator.storage.persist()`). |
| **Disk of the computer** | Normal files, for example the `.duckdb` file of an area | Fast | The size of the disk | Until the person removes them |

A page in the browser cannot open a normal file on the computer by its path. It can read a file that the person chooses, or files from a
URL. Only a program on the computer (way D) uses the disk of the computer directly.

**The browser disk is not a second memory.** A file on the browser disk uses no memory until the page reads a part of it. So a page that
keeps a large table as a file, and reads only the rows of a query, uses little memory.

**Some browsers cannot write to the browser disk:** some Safari versions and private windows. A page must then keep its data in memory, as
before, so it can show a smaller area only.

### Each way and the three places

| Way | Memory | Browser disk (OPFS) | Disk of the computer |
|---|---|---|---|
| A. One HTML file | The whole file, and all the data in it | Not used | The person keeps the HTML file |
| B. Files on a server | The tiles and the rows in view | Not used. The browser keeps the files it read in its HTTP cache. | Not used |
| C. Made in the browser | The engine, the tiles in view, and the tables with the home `memory` | The Parquet files of the tables (a table with the home `disk` is read from its file), and the terrain file | Not used |
| D. Made by a local program | The tiles and the rows in view | Not used | The program reads the input files there |

duckOSM Studio is an example of way C. Each tab has its own folder on the browser disk. A new build removes the files of the build before
it, and the folders of the tabs that closed, so the browser disk keeps the tables of one area for each open tab.

## The four ways to run a dashboard

| Way | Where the data is | Use it for | How to make it |
|---|---|---|---|
| **A. One HTML file** | In the file | A small area. A file to send, or to open from the disk. | [Make way A](#make-way-a-one-html-file) |
| **B. Files on a server** | In files at a URL. The browser reads only the parts that it needs (HTTP range requests). | A large area. A website or another map app. | [Make way B](#make-way-b-files-on-a-server) |
| **C. Made in the browser** | The page makes the data from its input files. It keeps the result in memory or on the browser disk (OPFS). | A page that builds its maps itself, for example duckOSM Studio. | [Make way C](#make-way-c-made-in-the-browser) |
| **D. Made by a local program** | A Rust program on the computer reads the input files on the disk and makes the tiles and the rows when the page asks for them. The browser only draws. | An area that is too large for the browser. A tool on one computer, for example `duckosm studio`. | [Way D](#way-d-the-engine-out-of-the-browser) |

**duckOSM's online and offline versions.** duckOSM makes its data in two of these ways:

| Version | Way | Program | Where the tables are | Its limit |
|---|---|---|---|---|
| Online | C | duckOSM Studio, a web page | Today in the memory of the tab. Planned (duckOSM's stage 3): Parquet files on the browser disk (OPFS), which DuckDB-Wasm reads in place (`registerFileHandle`) | The memory of the tab, then the space of the browser disk |
| Offline | D | `duckosm-rust` and `duckosm studio`, on the computer | In a `.duckdb` file on the disk; the program's DuckDB loads the PBF file (`read_osm`) | DuckDB's `memory_limit` and the disk (the load step of France, a 5.1 GB file, is measured in it) |

The two versions use the same engine and the same dashboard. Only the transport changes ([duckOSM's design note of the load step](https://github.com/Khoshkhah/duckOSM/blob/main/docs/design/streaming_load.md)).

The file formats are the same in the four ways: PMTiles for the tiles, and Parquet for the tables. Only the transport changes. A static file
host is enough for way B, and no running server is necessary. Way D is way C with the engine out of the browser: the same engine runs as a
program, and the data stays on the disk of the computer, not on the browser disk. [Make tiles and PMTiles](../rust/tiles.md) tells how to make the files.

### Make way A: one HTML file

Give the roads to Python, and save one file. The roads go into the file as tiles.

```python
import roadstyle as rs

rs.render_edges(edges).save("map.html")                 # a map
rs.render_dashboard(edges, ...).save("dashboard.html")  # a dashboard: the map, the panel and the toolbox
```

Or, with the roadstyle program, from a GeoParquet file of roads:

```bash
roadstyle page roads.parquet out/map.html
```

Open the file from the disk, or send it. It needs no server. The whole file goes into the memory of the tab, so use it for a small area.
More: [Dashboards](dashboards.md), [Make tiles and PMTiles](../rust/tiles.md#a-put-the-tiles-in-one-html-file).

### Make way B: files on a server

Make the files one time, and put them on a file host:

```python
rs.export_style(edges, "monaco_pm", base_url="https://example.org/monaco", format="pmtiles")
```

Or, with the roadstyle program, in two stages:

```bash
roadstyle sources roads.parquet out/stage1 --format geoparquet   # stage 1: the style and its sources
roadstyle tiles out/stage1 out/roads.pmtiles                     # stage 2: the tiles, as one PMTiles file
```

Put the folder on a web server at `base_url`. The server must answer HTTP range requests (most file hosts and cloud storage do). A map
opens `style.json` by its URL and reads each tile in view from `roads.pmtiles`. To show a change, make the files again.

The folder also has `props.json`: the fields of each road, in the order of the rows (a tile's feature id is its row). A dashboard reads
the folder with the adapter of way B, `rsFilesAdapter(base)` (`dashboard/ways.js`):

```js
import {filesAdapter} from "./dashboard/ways.js";

maplibregl.addProtocol("pmtiles", new pmtiles.Protocol().tile);          // the PMTiles library (vendor/pmtiles.js)
const adapter = filesAdapter("https://example.org/monaco");               // style.json, roads.pmtiles, props.json
rs.setAdapter(adapter);                                                    // rs: the page's dashboard (rsDashboard)
await rs.roadLayers({prefix: "rs-"}).show(await adapter.style());
```

A click on a road reads its row from `props.json`. The page reads the file one time, at the first click. The data dock needs a database:
give the adapter `query` and `schema` (for example DuckDB-wasm on Parquet files at the URL), else the dock says that the page has none.
More: [Make tiles and PMTiles](../rust/tiles.md#b-put-the-tiles-on-a-server), [The roadstyle program](../rust/cli.md).

### Make way C: made in the browser

The page loads the WebAssembly engine (roadstyle-wasm) and its input file. The engine makes each tile when MapLibre asks for it:

```js
import init, {resolveLook, styleSources, Tiler} from "./pkg/roadstyle_wasm.js";
import {rsDashboard} from "./dashboard/index.js";
import {engineAdapter} from "./dashboard/ways.js";
import {roadLayers} from "./dashboard/roadlayers.js";

await init();
const roads = new Uint8Array(await (await fetch("roads.parquet")).arrayBuffer());   // or a File from the browser disk
const map = new maplibregl.Map({container: "map", style: "https://tiles.openfreemap.org/styles/positron"});

let tiler = null, gen = 0;                                  // the tile address: rs://<generation>/<source>/<z>/<x>/<y>
maplibregl.addProtocol("rs", async ({url}) => {
  const [g, source, z, x, y] = url.slice("rs://".length).split("/");
  return {data: +g === gen ? tiler.tile(source, +z, +x, +y) : new Uint8Array()};
});
const look = resolveLook(JSON.stringify({palette: "amber", args: {state: "live"}}));
tiler = new Tiler(roads, look, undefined, "Area", `rs://${++gen}/`, ["name", "highway"]);
const sources = styleSources(roads, look);                  // the road table: the fields and the line of each road
const adapter = engineAdapter({tiler, sources});            // the adapter of way C (dashboard/ways.js)
const rs = rsDashboard(map, {style: null, prefix: "rs-", tiles: true, adapter});
await roadLayers({map, dashboard: rs, prefix: "rs-"}).show(await adapter.style());       // the roads over the base map
```

A click on a road reads its fields from the road table of `sources` (`roadTable`, read one time), and its line from `roadLines`. The data
dock needs a database: give the adapter `query` and `schema` (for example DuckDB-wasm on the Parquet files of the page).

A page that builds large areas runs the engine in a worker (the map worker), and keeps its tables on the browser disk
([Tables](#tables-in-memory-or-on-the-disk)). Its adapter gives the same functions, and each one asks the worker. The engine takes at most
200,000 roads. duckOSM Studio is a full example: it gives the dashboard its road table and its DuckDB-wasm with the host functions of
before (`window.RS_SIDE`, the data dock's `query` and `schema`), which work with no adapter.
More: [Use roadstyle in the browser](../rust/browser.md).

### Way D: the engine out of the browser

```bash
roadstyle local roads.parquet                       # the page at http://127.0.0.1:8830/local/
roadstyle local roads.parquet --table sensors=sensors.parquet --frames run.parquet --port 8840
```

`roadstyle local ROADS` starts a Rust program on 127.0.0.1. It reads a GeoParquet file of roads from the disk and answers the
[four requests](#the-four-requests-and-the-four-adapters) of the dashboard when the page asks:

| Request | Address | Made by |
|---|---|---|
| The style of the roads | `GET /style.json` | the engine (`relevel::LiveTiles`, with the tile rules of `tiled_sources`) |
| A tile | `GET /tiles/roads/<z>/<x>/<y>` | the engine (`LiveTiles::tile_in`): the tile of the map worker, byte for byte |
| Rows | `POST /rows/roads`, a list of row numbers | the engine (the road table) |
| The lines of roads | `POST /lines`, a list of row numbers | the engine (`write_road_lines`) |
| A query, the tables | `POST /query`, `GET /schema` | DuckDB on the Parquet files: the roads file is the table `roads`; `--table NAME=FILE` adds more |
| A window of frames | `GET /frames?from=<i>&to=<j>` | DuckDB on the file of a run (`--frames`: the columns `frame`, `t`, `row`, `value`) |
| A redraw with new levels | `POST /relevel`, rows of `levels.csv` | the engine (`LiveTiles::relevel`); see "The redraw of way D" below |
| The whole road table, the ends of the roads | `GET /road_table`, `GET /road_ends` | the engine (`write_road_table`, `road_ends`): the level editor (`levelEditPart`) borrows them while it is open, on a page that keeps no road table |
| The 3D walls | `POST /walls` (the GeoJSON of `rsSetWalls`), then `GET /tiles/walls/<z>/<x>/<y>` | the engine (`LiveTiles::set_walls`): the walls as tiles of the map, as the map worker of way C cuts them |

The page at `/local/` is the standard dashboard. It uses the adapter `rsHttpAdapter(location.origin)`
([the adapter](../reference/javascript.md)) and keeps no road table: a click on a road asks the program for its row, and a query of the
data dock runs in the program. The program holds the roads, so the page holds only what is in view.

A browser tab has limits: its memory (a WebAssembly module can use at most 4 GB) and the space of the browser disk. Way D has no such
limits, because the engine runs as a program on the computer:

- The program reads the input files on the disk and keeps them there.
- The page asks the program for each tile, one row for a popup, a query of the data dock, or a window of frames, at addresses on
  127.0.0.1.
- The page and the dashboard are the same as in ways B and C. Only the adapter changes, so the dashboard does not know which way it uses.

The server is the small Rust server of `roadstyle levels edit` and `roadstyle design edit` (roadstyle-serve), with one more thing: a
program can give it addresses of its own. The server only moves bytes. The functions behind the addresses call the engine or DuckDB, so
the program has no rule of its own for a tile, a row or a line. A test keeps the tiles equal: `way_d_tiles.json` holds the size and
hash of three tiles of Monaco. The native tests (`roadstyle-local`) and the WebAssembly package in Node (way C,
`cross_language.mjs`) both check the same file.

**A program that uses the crate** (for example `duckosm studio`) can give `roadstyle_local::Config` more than the command line gives:
the base-map rows (`features`: the buildings, the water and the other layers of the look go in the tiles, as `tiled_of` puts them),
and a `.duckdb` file (`database`: it is opened read only, and each of its tables is a table of the queries and the schema, in its own schema, for example `driving.edges`).
The tiles of way D are made by `tiled_sources`, the stage 2 of `tiled_of`, so the look's tile keys (`tile_format`, `tile_layers`,
`tile_keep`) apply.

**The redraw of way D.** The program holds the map as `relevel::LiveTiles`. `POST /relevel` takes rows of `levels.csv` (the level
editor's changed roads) and draws these roads again: the answer has the counts and, when the layers changed, the new style. A host
that saves the levels into the `.duckdb` file calls `Local::reopen_database`, and the queries then read the new tables. A program
with a server of its own serves the level editor's WebAssembly package with `roadstyle_serve::embedded`.

**Not in the command line yet:** the base-map rows and a `.duckdb` file as the input (only a program that uses the crate gives them).
The first user of the frames in the page (`rs.setFrames`) is planned.

**Way B and way D.** For the page they are the same: the same dashboard makes the same requests, and it gets the same tiles and rows.
Only the adapter is different (`rsFilesAdapter` reads files, `rsHttpAdapter` asks a program). The difference is who makes the data, and when:

| | B. Files on a server | D. Made by a local program |
|---|---|---|
| When the data is made | Before the page opens: you make the PMTiles and Parquet files one time | When the page asks for it, tile by tile |
| What answers the page | A file host. It runs no code. | A Rust program that runs while the page is open |
| A change (an edit, a new look, new values) | Make the files again | Shows at once: the program makes the new tiles |
| A query of the data dock | The host's DuckDB-wasm in the browser reads parts of the Parquet files (the adapter's `query`) | DuckDB in the program queries the files, and the page gets only the result |
| Who can open the page | Each person who has the URL, from any computer | Only the person on that computer (127.0.0.1) |
| Disk space | All the tiles of all zooms | Only the input files |

Use way B to show finished data to many persons. Use way D to build or edit a large area on one computer.

### Later: way D on a shared server

**An idea, not planned yet.** The program of way D can also run on a shared server, for many persons at one time. It is then a GIS server
for roadstyle, like GeoServer or QGIS Server: it makes the tiles and answers the queries when a map asks, and it lets persons edit the data.

| | Way D (one computer) | Way D on a shared server |
|---|---|---|
| Persons | One, on the same computer (127.0.0.1) | Many, from other computers |
| Read and write | Yes | Yes |
| Who can write | The person on the computer | Only the persons who have the right: the server must have sign-in and rights |
| Two persons edit the same feature | Cannot occur | The server must find the conflict and keep both edits safe |
| Other GIS apps (QGIS, ArcGIS) | Not necessary | Can use it when the server also gives the standard addresses: OGC API Tiles and OGC API Features (or WMTS and WFS-T) |

The engine, the file formats, the dashboard and the four requests stay the same as in way D. The shared server adds only the sign-in,
the rights, the conflict check and the standard addresses.

## One code for the four ways

The four ways are different only in the **transport**: how the bytes go from the data to the map. All other code is written one time,
and the four ways use it. This keeps the four ways equal: a change or a fix in one place is in all four ways.

### The parts of a dashboard

| Part | What it does | The one code | What changes from way to way |
|---|---|---|---|
| **Engine** | Cuts the tiles with the one tile rule, makes the look, the 3D walls, the terrain tiles and the levels | The Rust crates (`roadstyle`, `roadstyle-tiles`) | Only how it is compiled: the Python binding (A), a native program (B: makes the files; D: answers the page), WebAssembly (C) |
| **File formats** | Hold the data | PMTiles with MLT tiles; Parquet | Nothing |
| **Dashboard** | The map, the panel, the toolbox, the popups, the filters, the colours, the editors | `static/dashboard/` | Nothing |
| **Four requests** | What the dashboard asks for: a tile, one row, a query, a window of frames | One interface in the dashboard | Nothing for the dashboard. Each way gives one adapter. |
| **Transport** (the adapter) | Moves the bytes of each request | One small adapter for each way | Everything that is different is here, and only here |

### The four requests and the four adapters

| Request | A. One HTML file | B. Files on a server | C. Made in the browser | D. Made by a local program |
|---|---|---|---|---|
| **A tile** of a source at `z/x/y` | From the PMTiles archive in the file | A range request to the PMTiles file | The map worker cuts it | A request to the program |
| **One row** of a source (for a popup) | From the table in the page | From `props.json` at the URL, read one time | From the engine's road table (`Sources.roadTable`) | A request to the program |
| **A query** (the data dock, Ask) | The host's DuckDB-wasm | The host's DuckDB-wasm on the Parquet files at the URL | The host's DuckDB-wasm on the Parquet files in memory or on the browser disk | DuckDB in the program |
| **The adapter** (`dashboard/ways.js`) | None | `rsFilesAdapter(base)` | `rsEngineAdapter({tiler, sources})` | `rsHttpAdapter(base)` |
| **A window of frames** | The host gives them | DuckDB-wasm on the Parquet file at the URL | DuckDB-wasm on the browser disk, or a running simulation | The program |

### The rules that keep one code

1. **The engine has each function one time, in Rust.** The WebAssembly module and the native program call the same function. An address
   of the program in way D only calls that function. It has no logic of its own.
2. **The dashboard never asks which way it runs in.** It makes the four requests, and the adapter answers them.
3. **The files of way B come from the same engine** (`roadstyle tiles`, `Tiler.archive`). They are the same tiles that ways C and D make
   on request.
4. **A transport moves bytes, and never changes them.** The same request gives the same bytes in the four ways. A test can compare them.
5. **A new type of data is added one time.** It is a new source in the engine and a new name in the requests, not new code for each way.
6. **A host gives roadstyle functions, not data.** For example, `rsSetWalls` takes a function that gives the walls when they first show.
   The host decides the transport inside the function, and roadstyle does not change.

### What is one code today

| Part | Today |
|---|---|
| Engine | One code. The Python binding, the native program and the WebAssembly module call the same Rust crates. |
| Tiles | One code: one tile rule and one format for all ways. In way A, every layer is a tile layer of the archive in the file, except the 3D bridge decks (GeoJSON until they are tiles). |
| Dashboard | One code for all pages. |
| Four requests | One interface: the **adapter** (`dashboard/adapter.js`, [the design](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/memory_budget.md)). A page gives it one object with `tile`, `rows`, `query` and `frames` (and `lines`, `schema`, `style`); the dashboard asks the four requests through `rs.request`. Each way gives its own adapter. A page that has its road table in itself needs none, and the host functions of before (`window.RS_SIDE`, the data dock's `query` and `schema`) work as before. The first user of `frames` (`rs.setFrames`) is not built yet. |
| Adapters | One module, `dashboard/ways.js`, with no import: `rsFilesAdapter` (B: tested in a browser on the files of `export_style`), `rsEngineAdapter` (C: tested in Node with the WebAssembly package, `cross_language.mjs`) and `rsHttpAdapter` (D: `roadstyle local`, the crate `roadstyle-local`, answers it). Way A needs none. A way with no program (B, C) takes the data dock's `query` and `schema` from the host. |

## The types of data

| Type of data | How it is cut | A. One HTML file | B. Files on a server | C. Made in the browser | D. Made by a local program |
|---|---|---|---|---|---|
| [Road lines](#road-lines-and-other-layers) | Tiles | Tiles in the file | Tiles from the PMTiles file | The map worker makes a tile when the map asks for it | The program makes a tile when the map asks for it (built) |
| [Other layers](#road-lines-and-other-layers) (water, land, buildings, boundary) | Tiles | Tiles in the file (the rows of an overlay are also in the page) | Tiles | Tiles from the map worker | Tiles from the program (built: a program that uses the crate gives the rows, as `duckosm studio` does; the command line reads roads only) |
| [3D objects](#3d-objects) (walls, bridge decks, piers) | Pieces by tile | All objects at one time (planned: by tile) | Planned: by tile | Walls: tiles from the map worker. Decks: all at one time (planned: by tile). | Walls: tiles from the program (`POST /walls`, built). Decks: planned |
| [The ground](#the-ground) | Tiles of one terrain file | The terrain file at a URL | Tiles from the terrain file | A terrain file on the browser disk | Planned: the terrain file on the disk, by tile from the program |
| [Tables](#tables-in-memory-or-on-the-disk) (road fields, popups, queries) | Rows, read by query | The road table in the page | The rows from `props.json`; the queries by the host (Parquet at a URL) | The engine's road table; the queries by the host (in memory or on the browser disk) | The program queries the Parquet files and a `.duckdb` file on the disk with DuckDB (built) |
| [Values in time](#values-in-time) | Frames | One table of values at a time | One table of values at a time | One table of values at a time (planned: a window of frames) | The program gives the frames of the window (built; the page does not use them yet) |
| [Moving points](#moving-points) (vehicles) | Frames | Planned | Planned | Planned | Planned |

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
All ways give the same tiles ([Big networks](big-networks.md)):

- **A:** the tiles are in the HTML file.
- **B:** the browser reads each tile from the PMTiles file with a range request.
- **C:** the map worker keeps the roads and cuts a tile only when the map asks for it.
- **D:** the local program does the same as the map worker, outside the browser.

The other layers follow the same rule. In way A, they are tile layers of the archive in the file. The tiles have only the keys that the style reads, so the page also keeps the rows of each overlay (all its properties and its box) for `rsQuery`, `rsGetProps`, `rsFocus` and the popups. The 3D bridge decks stay GeoJSON until they are cut into pieces by tile.

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

In way D, the program queries the Parquet files on the disk with DuckDB, and the page gets only the result. In way B, the host reads the Parquet files at a URL. DuckDB-wasm reads only the row groups that a query needs. In way A, the page has
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
