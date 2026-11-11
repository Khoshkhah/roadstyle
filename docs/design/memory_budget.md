# Memory: one budget for every dashboard

Date: 2026-11-09, version 2. Status: proposal; step 0 (the measurement, 2026-11-10), the 3D walls and step 1 (every layer as tiles, 2026-11-10) are done. Version 1 covered the
roads and the time data. Version 2 adds every layer and the 3D objects, after a look at the data of urbanstyle and SimReady ("What the projects hold" below). "Step 0: the memory of a page" below
has the first measurement of a tab.

## Summary

A roadstyle dashboard must not run out of memory when the area is large, when it has many layers, or when the data has a time dimension.
Examples are duckOSM Studio (a large area), urbanstyle (many layers of street space and 3D bridges), SimReady (lanes and junctions) and
roadstyle-sim (a microsimulation, with values for each road at each time step and, perhaps, moving vehicles). Their files and their sizes
are different, and they change. So the design must not depend on one project's data.

Today only the roads are safe in all paths: the map has them as tiles, and only the tiles in view are in memory. Four other parts grow with the
size of the data:

1. **The other layers** (overlays: lanes, marks, street objects, surfaces) are GeoJSON sources in the embedded page. MapLibre loads all of
   each one at the start.
2. **3D objects** are made from all the features of their source at one time.
3. **The road table** has one JavaScript object for each road.
4. **Live data** (`rs.setData`) takes rows as objects and makes a new map of objects at each call. A simulation that calls it for each frame
   makes all of this again at each frame.

This note gives one rule and one design for each kind of data. All dashboards use the same design, so a new project needs no special code for
memory.

## The rule

**Cut everything by place (tiles) and by time (a window). The memory of a page grows with the view and with the time window. It does not grow
with the area, the number of layers or the length of the data.**

| Kind of data | Memory must grow with | Must not grow with |
|---|---|---|
| 2D geometry of every layer (roads and overlays) | The tiles in view | The number of features |
| 3D objects (bridge decks, piers, later buildings and trees) | The tiles in view | The number of objects in the area |
| Attributes of every layer | The columns that the page reads for many features at a time, in compact arrays | The number of fields, or one object for each feature |
| Time data | The roads × the frames in the window | The length of the run |
| Moving points | The points in the window | The length of the run |

A CI test keeps the rule (part 6 of the design).

## What the projects hold

These are file sizes and row counts, measured on 2026-11-09. They are not the memory of a tab.

**urbanstyle, the Monaco page** (`viz/monaco.html`, made 2026-10-23, a 34 MB file). The page has 25 sources as gzip GeoJSON in the file.
Unzipped:

| Sources | GeoJSON | Features |
|---|---|---|
| The roads (`roads`, `simple`, `slots`) | 18.7 MB | 31,052 |
| The 22 overlays (lanes, marks, street objects, surfaces, ...) | 87 MB | about 50,000 |
| All | **106 MB** | about 81,000 |

The largest overlay is 24 MB of GeoJSON (9,778 features). Monaco is about 2 km². A city with the same density and 50 times the area
(Vancouver city) has about 5 GB of GeoJSON. This is an estimate. A cut of Vancouver (`viz/cut-vwide2.html`) is already an 82 MB file.

**urbanstyle, the 3D bridges.** The page loads the bridge file (`<name>.bridge3d.json`) in one piece. One corridor (Broadway and Granville)
is 10.4 MB. The sloped deck mesh (`dashboard/bridgemesh.js`, on the branch `claude/bridge-mesh-3d`, not on `main`) makes one mesh from all the
features of the source `decks` (`_sfeats("decks")`).

**SimReady, Tartu** (`out/tartu-rust/build.duckdb`, 482 MB):

| Table | Rows |
|---|---|
| `sim.attribute` | 731,282 |
| `sim.elevation_profile` | 409,008 |
| `sim.kerb_profile` | 250,541 |
| `sim.event` | 76,452 |
| `sim.lane` | 24,139 |

`connectors.parquet` is 60 MB. Tartu is a small city.

**A simulation, an estimate for a city of the size of Vancouver** (345,000 cycling edges in `vancouver_city.osm.duckdb`):

| Data | Size |
|---|---|
| One `Float32` value for each road, 1 hour at 1 s steps (3,600 frames) | 5 GB |
| 50,000 vehicles at 10 frames each second for 1 hour, 16 bytes for each vehicle | about 29 GB |

So no project can load all its data. The window and the tiles are necessary, not an option.

## What roadstyle holds today

| Part | Where | How it holds the data |
|---|---|---|
| Road geometry | `roadstyle-tiles`, the map worker, the embedded PMTiles archive | Tiles. A road feature has only its marks and some keys ([tiling.md](tiling.md)). Safe. |
| Overlay geometry | The embedded archive, the map worker, the server tiles | Tiles (2026-11-10, "Step 1" below). The embedded page also has the overlay's rows (properties and box), one object for each feature, until step 2. `decks` and `shadows` stay GeoJSON until step 5. |
| 3D objects | Fill-extrusion layers of the source `decks`; the mesh of `bridgemesh.js` (branch) | All features of the source at one time. |
| 3D walls by type | `dashboard/walls.js`; the engine's `walls.rs` | Tiles (2026-11-10). The page gives a function to `rsSetWalls`. It runs only when "Walls by type" is on. The map worker cuts the strips and the roofs into a tile layer `walls` (zoom 14 to 16) and keeps no GeoJSON. A page that gives a FeatureCollection still gets a GeoJSON source ("The 3D walls", below). |
| Road table, in the page | `RoadTable` in `dashboard/core.js` (`props`, `mids`, `bboxes`, `lines`) | One JavaScript object for each road in `props`, and one array for each road in `mids` and `bboxes`. The engine sends it as JSON text (`roadTable()` in `roadstyle-wasm`), and the page parses all of it. |
| Road table, in the engine | `LiveTiles` and `Tiler` in `roadstyle-wasm` | The roads in Rust memory. `props(source, id)` already gives the fields of one feature. |
| Live data | `setData` in `dashboard/live.js` | The rows as objects (an Arrow table becomes objects through `toArray()`), a `Map` from row to joined row, and a `Map` from row to colour. |
| Live colours | `_applyC` in `dashboard/color.js` | One `setFeatureState` call for each road whose colour changed. |

### The 3D walls (measured 2026-11-10, done)

Before this change, Studio gave all the walls to `rsSetWalls` after each draw, also when "Walls by type" was off (the default). `walls.js`
kept them as one GeoJSON source, and MapLibre kept every wall in one worker:

| Area | Walls | That worker | The tab |
|---|---|---|---|
| Tartu | 164,482 (50 MB of GeoJSON) | 605 MiB | not measured here |
| Burnaby | 350,670 | 1,353 MiB | 4,180 MiB. With the walls shown at zoom 16, the tab stopped (out of memory). |

A prototype that cut the walls into tiles of zoom 14 to 16 gave the same picture (Monaco: 3,820 against 3,819 features in view), the wall
worker 72 MiB, and no crash on Burnaby.

Now (two changes):

1. **Nothing until the walls show.** `rsSetWalls` takes a function. `walls.js` calls it once, when "Walls by type" is on and the 3D buildings
   show. With the walls off, the page has no wall data at all.
2. **Tiles.** The function gives the vector source of `LiveMap.setWalls` (roadstyle-wasm): the map worker's engine makes the strips
   (`rust/roadstyle/src/walls.rs`, the rule of `walls.js`) and cuts them with the one tile rule into the layer `walls`, from zoom 14 to the map's last
   zoom. The worker cuts a tile only when MapLibre asks for it, as it does for the roads. The address is the roads' address with the source
   `walls`: `<prefix>walls/{z}/{x}/{y}`.

Studio's measurement of the change is in the pull request of Studio's roadstyle pin (Tartu, the tab after the draw with the walls off, before and after).

So the road attributes are in memory two times: in Rust, and as JavaScript objects. A JavaScript object with 20 fields uses much more memory
than the same values in a column. I did not measure how much.

Studio's measurement of Burnaby (151,770 roads, 2026-11-04) gives the tab 3,174 MiB. The map worker, DuckDB-wasm and the build module give
1,519 MiB together. About 1,650 MiB has no owner in that measurement. My estimate is that most of it is the road table as objects. This is a
subtraction, not a measurement.
Step 0 (below) does not support this estimate: the road table of Tartu's page is 38 MiB for 63,965 roads, so Burnaby's would be about
90 MiB, not 1,650 MiB. Studio's other parts (DuckDB-wasm, its tables, the build) are Studio's, not roadstyle's.

### Step 0: the memory of a page (measured 2026-11-10)

The pages: `roadstyle.duckosm.page(db, dashboard=True, live_data=True)` of duckOSM's Monaco and Tartu files, roadstyle `c6e71cb4`, in headless
Chromium (1280 × 800, the start view of the area). No Studio. The script is `scripts/measure_memory.py`:

- **The tab:** the private memory of the tab's renderer processes (`Private_Clean` and `Private_Dirty` of `/proc/<pid>/smaps_rollup`).
- **JS heap:** the heap of the page and of each worker after a garbage collection (the DevTools protocol: `HeapProfiler.collectGarbage`,
  `Runtime.getHeapUsage`). `performance.measureUserAgentSpecificMemory` is not available in this Chromium.
- **A part:** what the tab and the heaps give back when the page lets that part go. The overlays: their layers and GeoJSON sources removed.
  The road table: `window.RS_SIDE = null`. Live data: one `rs.setData` with one value for each road, then `rs.clearData`.

| | Monaco | Tartu |
|---|---|---|
| Roads | 13,298 | 63,965 |
| Overlays (sources), features | 17, 2,536 | 16, 31,526 |
| The road table as JSON text | 10.7 MB | 51.7 MB |
| The overlays as GeoJSON text | 1.1 MB | 12.1 MB |
| **The tab, loaded** (a run differs by about 2 MiB) | **94 MiB** | **207 MiB** |
| JS heap, loaded: the page, the map worker | 24, 9 MiB | 74, 51 MiB |
| **The overlays** (tab; page heap, worker heap) | 9 MiB; 2, 3 MiB | **67 MiB; 14, 41 MiB** |
| **The road table** (tab; page heap) | 10 MiB; 9 MiB | **41 MiB; 38 MiB** |
| Live data, one value for each road (tab; page heap) | 1 MiB; 0 MiB | 3 MiB; 6 MiB |
| The rest (the tab without the overlays and the table) | 75 MiB | 99 MiB |

What this shows:

1. **The overlays are the largest part** that grows with the area: on Tartu a third of the tab, most of it in the map worker (MapLibre's
   GeoJSON index). They are also the largest part for urbanstyle (87 MB of overlay GeoJSON on Monaco, "What the projects hold"). So step 1
   (every layer as tiles) stays first.
2. **The road table is second:** 38 MiB of page heap for 52 MB of JSON text, about 600 bytes for each road. Step 2 (columns) stays second.
3. **Live data is small for one frame** (3 to 6 MiB for 63,965 roads). The cost of live data is the frames of a run (step 3), not one table.
4. The rest (75 to 99 MiB) is the browser, MapLibre and the dashboard code; it does not grow much with the area.

The order of the plan does not change.

### Studio's prototype (measured 2026-11-10, not merged)

Studio's branch `claude/proto-wall-tiles` tried the walls as tiles on the browser disk (OPFS) and Studio's tables on the disk, in headless
Chromium. It is a Studio page, so DuckDB-wasm and Studio's tables are in the tab too. The numbers show what a large host holds beside roadstyle:

| Area | The tab | Parts |
|---|---|---|
| Monaco | 801 to 871 MiB | |
| Tartu | 2,225 MiB | the walls' worker 605 MiB, the map worker 192 MiB, DuckDB 206 MiB, the road table 23 MiB |
| Burnaby, before | 4,180 MiB | the walls' worker 1,353 MiB; the tab stopped with the walls on |
| Burnaby, the prototype | 2,193 MiB | DuckDB 50 MiB, the walls' worker 72 MiB |

The speed of the disk path:

- A popup's query on a Parquet file on the disk: 20 ms on Monaco; on Burnaby 52 ms mean, 11 ms median.
- A wall tile: 0.25 ms from the memory cache, about 1.2 ms from OPFS, 2.9 to 4.4 ms mean to make it.

So step 7 (the OPFS transport) is fast enough for a popup and for tiles. roadstyle's walls are now tiles of the map worker ("The 3D walls"
above); Studio's tables on the disk are Studio's own work.

### Step 1: every layer in the embedded archive (done 2026-11-10)

The embedded PMTiles archive of a one-file page (way A) had the road layers only. Now it has a tile layer for each source: the base map, the
boundary and the overlays too (`tiled_page` in `page_options.rs`). The page keeps no GeoJSON for them. Only `decks` and `shadows` stay
GeoJSON (step 5): the dashboard reads all their features at one time.

The tiles of an overlay have only the keys that the style reads. The dashboard needs more from an overlay: `rsQuery(test, layer)` runs a
test over each feature, `rsGetProps` reads rows, `rsFocus` needs the box of a feature, and a popup reads its fields. So the page also holds
the **rows** of each overlay: all its properties and its box (`__rs_bbox`), as JSON, gzip, and a `data:` URL in
`roadstyle:interaction.base_props` (`rows_file` in `lib.rs`; the page option `overlays[].props`). `overlays.js` reads them when the page
starts and gives `_sfeats` a feature with no geometry for each row (`OV_ROWS` in `core.js`). The rows are one JavaScript object for each
feature. Step 2 (columns) changes that.

Measured the same way as step 0: `scripts/measure_page.py` (the private memory of the tab, headless Chromium, a view of 640 × 400, a view of
zoom 16 with every overlay layer on), roadstyle on `main` against this change, 2026-11-10. The machine ran other builds, so a number can
differ by a few MiB between runs.

| Page | File | Tab, loaded | Tab, zoom 16, every overlay on |
|---|---|---|---|
| urbanstyle, Monaco (`viz/monaco.html`, 35 overlays, about 80,000 features) before | 34.7 MB | 587 MiB | 630 MiB |
| the same after | 19.1 MB | 416 MiB | 442 MiB |
| roadstyle, Monaco (`duckosm.page`, 16 base-map layers) before | 5.3 MB | 215 MiB | 334 MiB |
| the same after | 5.0 MB | 202 MiB | 271 MiB |

The pictures are the same: at zoom 16, 19.8 % of the pixels of the urbanstyle page and 4.5 % of the roadstyle page differ at all (the tile cut
and MapLibre's GeoJSON cut anti-alias a little differently), 0.09 % and 0.00 % by more than 32 levels of 255. `rsQuery(() => true, label)` gives
the same number of features for each of the 35 and the 16 overlays, `rsGetProps` the same field names, and `rsFocus` and `rsHighlight` the same camera
and state. The file is smaller because tiles are smaller than GeoJSON; the 5.4 MB of rows are in it.

What is left in memory: the rows (one object for each feature) and the browser. Step 2 turns the rows into columns, and the rows of a layer
that is off need not be loaded.

## The design

### Where the data lives

One set of file formats for every project, in two places:

| Data | Format | Outside the browser (a URL) | Inside the browser |
|---|---|---|---|
| 2D geometry of all layers | PMTiles (MLT tiles) | Read by tile with HTTP range requests | OPFS, or made by the map worker from the data in memory |
| 3D pieces | One file of mesh pieces, addressed by tile | Read by tile with range requests | OPFS, or made by the worker |
| Attributes, time data, points | Parquet, ordered by place or by time | DuckDB-wasm reads only the row groups that a query needs | OPFS, read by DuckDB-wasm |

The format is the same in the two places. Only the transport changes, as for the tiles today ([tiling.md](tiling.md), "The rule"). No running
server is necessary: a static file host is enough.

roadstyle knows no DuckDB ([ask_and_data_dock.md](ask_and_data_dock.md)). The host page (Studio, urbanstyle, roadstyle-sim) loads DuckDB-wasm
and gives roadstyle small functions: one feature's row, a window of frames. roadstyle can ship an optional helper that makes these functions
from Parquet files with DuckDB-wasm, for a host that does not want to write them.

### 1. 2D geometry: every layer is a tile layer

- Every source of the page is a tile layer with the one tile rule: the roads, the overlays, the boundary. This closes item 1 of "What is not
  one yet" in [tiling.md](tiling.md).
- An overlay feature in a tile has its geometry, its id and only the keys that the style reads, as a road feature has today. Its other
  fields are in the attributes (part 3).
- The embedded page and the map worker give the same tiles. The page does not keep the GeoJSON after the tiles are made.

This is the largest gain for urbanstyle: 87 MB of overlay GeoJSON on Monaco becomes the tiles in view.

### 2. 3D objects: pieces by tile

- The engine cuts the 3D objects (bridge decks, piers, girders, later buildings and trees) into pieces by tile, as it cuts lines. An object
  that crosses a tile border is in each tile that it touches.
- The page loads the pieces of the tiles in view, builds the mesh of each tile, and frees the mesh of a tile that leaves the view.
- A value that needs the whole object (the group height of a bridge, `__rs_group`) is computed by the engine once and written into each piece.
  The page does not need the other tiles to draw one tile.
- This is the idea of the OGC 3D Tiles standard. Whether roadstyle uses 3D Tiles files or its own pieces in the vector tiles is an open
  question (below).

### 3. Attributes of every layer: one copy, in columns

- The page keeps **no object for each feature**. `RoadTable.props(i)` asks the engine for one feature (`props(source, id)`, which exists), or
  asks the host for one row.
- The values that the page reads for many features at a time (the Roads filter, the search, `rs.setData`'s key) are **columns**: a typed
  array for a number, and a dictionary and an index array for a text.
- `mids` and `bboxes` become one `Float64Array` each (2 and 4 numbers for each road), not one array for each road.
- The same holds for the overlays: their popup reads one row by id.
- The API of `RoadTable` does not change. Only its inside changes, so most callers stay the same.

### 4. Time data: a window, never the whole run

roadstyle keeps the window, and the host gives the frames:

```js
rs.setFrames({
  frames: (from, to) => host.loadFrames(from, to),  // a Promise of [{t, values: Float32Array}], one value for each road row (NaN: no data)
  count: 3600,                                      // the number of frames in the run
  window: 60,                                       // the frames that stay in memory
  colorBy: {ramp: "viridis", range: [0, 2000]},     // as in rs.setData
});
rs.showFrame(i);                                    // draw frame i; roadstyle loads the window around i
```

- **The host decides where the frames come from:** Parquet in OPFS or at a URL through DuckDB-wasm, or a WebSocket from a running
  simulation. roadstyle does not depend on the source.
- **A frame is one `Float32Array` with one value for each road row.** 100,000 roads use 400 KB for each frame. A window of 60 frames uses
  24 MB, for any length of the run.
- **No objects for each road and each frame.** `rs.showFrame` turns the values into colours (and widths) with the ramp, and gives them to
  the map.
- `rs.setData` stays for one table at a time. It also accepts a column (`Float32Array` and the key column), so that it makes no objects.

**How a frame reaches the map** is the open technical question. Two ways:

| Way | Cost for each frame | Risk |
|---|---|---|
| A. `setFeatureState` for each road whose colour bucket changed (as `_applyC` does now) | One call for each changed road. With a ramp of 9 to 16 buckets, many roads keep their bucket from one frame to the next. | Not measured. When all roads change, the cost is one call for each road. |
| B. The worker writes the bucket into the tiles in view, and MapLibre loads those tiles again ([restyle_without_retile.md](restyle_without_retile.md) has the fast path) | The tiles in view | Not measured. A tile reload can make the map flicker. |

Step 3 of the plan measures both on Tartu and chooses one.

### 5. Moving points (vehicles)

Moving points follow the same window rule. Each frame has typed arrays (`x`, `y`, `heading`, `id` and a value), and the host gives them through
the same `frames` function. They go into one point layer whose data roadstyle replaces at each frame. Only the points in view are drawn. This part
waits until roadstyle-sim says that it shows vehicles.

### 6. A memory budget in CI

A test like the tile budget (`tests/test_tile_budget.py`):

- A synthetic network of a fixed size, with overlays and 3D decks, and a synthetic run of a fixed length.
- The test opens the page in Chromium, pans over the area, plays the run, and reads the memory of the tab
  (`performance.measureUserAgentSpecificMemory()`, or the heap size from the DevTools protocol).
- The memory must stay under a budget, and the budget can only go down.
- Three runs check the rule, not only one number. Each run must use about the same memory as the base:
  - 2 times the area.
  - 2 times the layers.
  - 2 times the length of the run.

## The plan

Each step has a check. A step starts only when the step before it is done. The test areas are Monaco and Tartu.

| Step | Work | Check |
|---|---|---|
| 0 | **Measure.** The memory of the tab, the map worker and the road table, on Monaco and Tartu, with the current code. Count the bytes of `RoadTable` alone and of the overlay sources alone. **Done 2026-11-10** on roadstyle's own pages ("Step 0: the memory of a page"); an urbanstyle page is not measured yet. | The numbers are in this note. They show which part is the largest. |
| 1 | **Every layer as tiles** (part 1). **Done 2026-11-10** ("Step 1" above). | The urbanstyle Monaco page looks the same (pixel test), and the overlay GeoJSON is not in memory after the tiles are made. |
| 2 | **Attributes in columns** (part 3). | The tests of the dashboard pass, the popups and the filters show the same values, and the memory of step 0 is lower. |
| 3 | **Frames** (part 4), with way A and way B behind one function. Measure both. First read roadstyle PR 149 (the vehicles: `rust/roadstyle-sim`, `vehicles.js`, `roadstyle-camera`), which is open. | A synthetic run on Tartu (1 hour at 1 s steps, 3,600 frames) plays at 10 frames each second, and the memory stays flat during the run. |
| 4 | **The CI budget** (part 6). | The test fails when a change adds an object for each feature, or when the memory grows with the area, the layers or the length of the run. |
| 5 | **3D pieces by tile** (part 2), after the bridge mesh is on `main`. The 3D walls are done (2026-11-10, "The 3D walls" above): the same way for the decks and the piers. | The bridges of the urbanstyle Monaco page look the same, and the mesh memory follows the view. |
| 6 | **Moving points** (part 5), if roadstyle-sim needs them. | The same budget test with points. |
| 7 | **OPFS transport** for tiles and Parquet, when a page builds more than the memory holds (Studio above about 200,000 roads). | The same tiles as the worker's tiles, byte for byte. |

The order puts the largest measured part first. Step 0 can change the order.

## Open questions for Kaveh

1. **The frame API:** do you accept that the host gives the frames through a function, and that roadstyle keeps only the window?
2. **The road table:** do you accept that `RoadTable` keeps its API but holds columns inside? Three places read `props` directly and
   must use `RoadTable` first: `dashboard/select.js` (line 38), `dashboard/editor/level_editor.js` (`RS_SIDE?.props`) and Studio's
   `index.html`, which sets `window.RS_SIDE` from `roadTable()`.
3. **3D pieces:** OGC 3D Tiles files (a standard that other viewers read), or roadstyle's own pieces in the vector tiles (one protocol with the
   2D tiles)?
4. **The optional DuckDB helper:** do you want roadstyle to ship it, or does each host write its own two functions?

## Not in this note

- The memory of the duckOSM build in the browser: `build-memory.md` in duckOSM Studio, `docs/proposals/`.
- The disk store of Studio's build result: `disk-store.md` in the same folder. Step 7 of this note is the roadstyle side of it.
