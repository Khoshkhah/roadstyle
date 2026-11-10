# Memory: one budget for every dashboard

Date: 2026-11-09. Status: proposal, not built. The numbers in this note come from earlier measurements of duckOSM Studio. This note adds no
new measurement. Step 0 of the plan makes the first measurement.

## Summary

A roadstyle dashboard must not run out of memory when the area is large or when the data has a time dimension. Examples are duckOSM Studio
(a large area) and roadstyle-sim (a microsimulation, with values for each road at each time step and, perhaps, moving vehicles).

Today the geometry is safe: the map has it as tiles, and only the tiles in view are in memory. Two other parts grow with the size of the data:

1. **The road table** has one JavaScript object for each road.
2. **Live data** (`rs.setData`) takes rows as objects and makes a new map of objects at each call. A simulation that calls it for each frame
   makes all of this again at each frame.

This note gives one rule and one design for each kind of data. All dashboards use the same design, so roadstyle-sim needs no special code
for memory.

## The rule

**The memory of a page grows with the view and with a time window. It does not grow with the area or with the length of the data.**

| Kind of data | Memory must grow with | Must not grow with |
|---|---|---|
| Geometry | The tiles in view | The number of roads |
| Road attributes | The number of roads × the bytes of one value, for the columns that the page reads | The number of fields, or one object for each road |
| Time data | The roads × the frames in the window | The length of the run |
| Moving points | The points in the window | The length of the run |

A CI test keeps the rule (step 5 of the plan).

## What roadstyle holds today

| Part | Where | How it holds the data |
|---|---|---|
| Geometry | `roadstyle-tiles`, the map worker, the embedded PMTiles archive | Tiles. A road feature has only its marks and some keys ([tiling.md](tiling.md)). Safe. |
| Road table, in the page | `RoadTable` in `dashboard/core.js` (`props`, `mids`, `bboxes`, `lines`) | One JavaScript object for each road in `props`, and one array for each road in `mids` and `bboxes`. The engine sends it as JSON text (`roadTable()` in `roadstyle-wasm`), and the page parses all of it. |
| Road table, in the engine | `LiveTiles` and `Tiler` in `roadstyle-wasm` | The roads in Rust memory. `props(source, id)` already gives the fields of one road. |
| Live data | `setData` in `dashboard/live.js` | The rows as objects (an Arrow table becomes objects through `toArray()`), a `Map` from row to joined row, and a `Map` from row to colour. |
| Live colours | `_applyC` in `dashboard/color.js` | One `setFeatureState` call for each road whose colour changed. |

So the road attributes are in memory two times: in Rust, and as JavaScript objects. A JavaScript object with 20 fields uses much more memory
than the same values in a column. I did not measure how much.

Studio's measurement of Burnaby (151,770 roads, 2026-11-04) gives the tab 3,174 MiB. The map worker, DuckDB-wasm and the build module give
1,519 MiB together. About 1,650 MiB has no owner in that measurement. My estimate is that most of it is the road table as objects. This is a
subtraction, not a measurement.

## The design

### 1. Geometry: tiles, with one more transport

No change to the tiles. For an area that is too large for the worker's memory, add one transport: a PMTiles archive in the browser's disk
(OPFS). The worker reads it with the same reader as a PMTiles archive from a URL. The archive has the same tiles as every other path, and a
transport never changes a tile ([tiling.md](tiling.md), "The rule").

This part is necessary only above about 200,000 roads (the guard of Studio). Do it after parts 2 and 3.

### 2. Road attributes: one copy, in columns

- The page keeps **no object for each road**. `RoadTable.props(i)` asks the engine for one road (`props(source, id)`, which exists) or reads
  it from columns.
- The values that the page reads for many roads at a time (the Roads filter, the search, `rs.setData`'s key) are **columns**: a typed array
  for a number, and a dictionary and an index array for a text.
- `mids` and `bboxes` become one `Float64Array` each (2 and 4 numbers for each road), not one array for each road.
- The API of `RoadTable` does not change. Only its inside changes, so the callers stay the same.

### 3. Time data: a window, never the whole run

roadstyle knows no DuckDB ([ask_and_data_dock.md](ask_and_data_dock.md)). So the host gives the frames, and roadstyle keeps the window:

```js
rs.setFrames({
  frames: (from, to) => host.loadFrames(from, to),  // a Promise of [{t, values: Float32Array}], one value for each road row (NaN: no data)
  count: 3600,                                      // the number of frames in the run
  window: 60,                                       // the frames that stay in memory
  colorBy: {ramp: "viridis", range: [0, 2000]},     // as in rs.setData
});
rs.showFrame(i);                                    // draw frame i; roadstyle loads the window around i
```

- **The host decides where the frames come from:** Parquet in OPFS through DuckDB-wasm, a file at a URL, a WebSocket from a running
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

Step 2 of the plan measures both on Tartu and chooses one.

### 4. Moving points (vehicles)

If a dashboard shows moving points, they follow the same window rule: each frame has typed arrays (`x`, `y`, `id`, and a value), and the host
gives them through the same `frames` function. They go into one point layer whose data roadstyle replaces at each frame. This part waits
until roadstyle-sim says that it shows vehicles.

### 5. A memory budget in CI

A test like the tile budget (`tests/test_tile_budget.py`):

- A synthetic network of a fixed size and a synthetic run of a fixed length.
- The test opens the page in Chromium, plays the run, and reads the memory of the tab (`performance.measureUserAgentSpecificMemory()`,
  or the heap size from the DevTools protocol).
- The memory must stay under a budget, and the budget can only go down.
- A second run with 2 times the length of the run must use about the same memory. This checks the rule, not only one number.

## The plan

Each step has a check. A step starts only when the step before it is done. The test areas are Monaco and Tartu.

| Step | Work | Check |
|---|---|---|
| 0 | **Measure.** The memory of the tab, the map worker and the road table, on Monaco and Tartu, with the current code. Count the bytes of `RoadTable` alone. | The numbers are in this note. They show whether the road table is the 1,650 MiB with no owner. |
| 1 | **Road table in columns** (part 2). | The tests of the dashboard pass, the popups and the filters show the same values, and the memory of step 0 is lower. |
| 2 | **Frames** (part 3), with way A and way B behind one function. Measure both. | A synthetic run on Tartu (1 hour at 1 s steps, 3,600 frames) plays at 10 frames each second, and the memory stays flat during the run. |
| 3 | **The CI budget** (part 5). | The test fails when a change adds an object for each road, or when the memory grows with the length of the run. |
| 4 | **Moving points** (part 4), if roadstyle-sim needs them. | The same budget test with points. |
| 5 | **OPFS transport** (part 1), when a page needs more than about 200,000 roads. | The same tiles as the worker's tiles, byte for byte. |

## Open questions for Kaveh

1. **roadstyle-sim:** does it show values for each road, moving vehicles, or both? How many roads, frames and vehicles at the peak? The
   answers set the window size and the budget of step 3.
2. **The frame API:** do you accept that the host gives the frames through a function, and that roadstyle keeps only the window?
3. **The road table:** do you accept that `RoadTable` keeps its API but holds columns inside? Three places read `props` directly and
   must use `RoadTable` first: `dashboard/select.js` (line 38), `dashboard/editor/level_editor.js` (`RS_SIDE?.props`) and Studio's
   `index.html`, which sets `window.RS_SIDE` from `roadTable()`.

## Not in this note

- The memory of the duckOSM build in the browser: `build-memory.md` in duckOSM Studio, `docs/proposals/`.
- The disk store of Studio's build result: `disk-store.md` in the same folder. Part 1 of this note is the roadstyle side of it.
