# Parity and speed

<p class="lead">About how the tests show that the Rust engine makes the same output as the Python engine, how fast it is, and how
much memory it uses.</p>

## What "the same" means

For the style and the page, the same means the same JSON values: the same keys, the same numbers to the last digit (the engine
parses floats exactly). The JSON text is each engine's own: since 2026-10-24 the Rust engine writes `serde_json`'s compact text, not
Python's `json.dumps` (the Rust API is the design), and the tests compare the values (`_same_page`).

For the tiles, the same means the same features when decoded: the same ids, properties and geometry. The bytes can differ,
because Python's encoder (`mapbox_vector_tile`) writes a negative integer as `int_value` and a float with no fraction as an
integer, and the engine writes `sint_value` and a double. MapLibre reads the same numbers from both.

## The goldens

Two kinds of golden check the Rust engine:

- **The Rust engine's own goldens** (since 2026-10-24, when the Rust API became the design). A golden is a summary of an output:
  each layer's id, type and source with short hashes of its filter, paint and layout; each source's type, feature count and hash;
  the metadata keys; the road table's rows and columns; for the tiles, the number of tiles and features of each zoom and tile layer
  with their hash; and the hash of the whole output. The goldens are a few KB each, in git. `ROADSTYLE_BLESS=1 cargo test` writes
  them again after a change that you decided, and a test that fails names the part that changed. `areas.rs` has the style and the
  tiles of Monaco, the Södermalm sample and Tartu (64,828 roads, with `--ignored`); `cases.rs` has the engine's cases on a part of
  Monaco, and `colors.rs` the data-driven colour cases on it.
- **Python's goldens** (`rust/roadstyle-rs/tests/make_goldens.py`), for what is still checked against Python: the levels (the tags
  rule and the solve) and the looks of each profile and palette (`look.rs`). The last check of the style, the tiles and the colour
  cases against Python was 2026-10-24 (audit 3's N27).

Tartu's inputs are on the GitHub pre-release `rust-test-data`; `get_goldens.sh` gets them and checks their SHA-256.

## The tests with both engines

| Test | What it shows |
|---|---|
| `tests/test_engine_parity.py` | The two engines give the same style, page, `export_style` files, look and levels on a part of Monaco, case by case: data colors, column names, caps, metre widths, overlays, decks, the full look, views, tiled pages, PMTiles |
| `ROADSTYLE_ENGINE=rust pytest` | The whole Python suite (561 tests on 2026-10-23) passes with the Rust engine as the default |
| `tests/test_contract_names.py` | The names of the interaction contract in the code are the names in the reference |

The CI workflow `.github/workflows/rust.yml` runs on each push to `main` or `rust-engine` that changes `rust/` or
`src/roadstyle/`, and on pull requests:

- the job `rust`: the goldens, `cargo test --release`, `cargo clippy -D warnings`, and the WebAssembly build;
- the job `python`: it builds `roadstyle._rust`, runs `tests/test_engine_parity.py`, then the whole suite with
  `ROADSTYLE_ENGINE=rust`.

Each night, CI also runs the Tartu goldens, which take longer.

## The differences that stay

Each difference that the goldens found has a cause and a decision. These stay:

| Difference | Cause | Decision |
|---|---|---|
| The nearest road of a name or arrow slot: 4 slots of Monaco, 10 of Tartu | The two directions of one way have the same line, so the slot is at distance 0 from both. GEOS's tree takes one of them, the engine takes the lower index | Keep: the name and the arrow are the same |
| The solve of Monaco: 8 of 13,298 rows | Python's linear program and the engine's minimum-cost flow take different answers among equal best ones. Both break 0 hard rules | Keep: equal quality by roadstyle's own rules. Södermalm is equal in all rows |
| The bytes of a tile | The two encoders write numbers in different forms (see above) | Keep: the tests compare decoded tiles |
| The corners of the 3D bridge decks | The engine makes the ribbons with its own mitre offsets, not with GEOS | Keep: the same to 1e-6 degrees |
| No Python solve golden for Tartu | Python's solve needs more memory than the test machine has | Keep: Monaco and Södermalm cover the solve |

## Speed

Measured on 2026-10-23 on one machine: an Intel Core i5-13600K (20 threads), 23 GB of memory, Linux (WSL2), Python 3.11, Rust
1.99.1, the release build. Each case ran in its own process; the memory is the peak resident memory of that process
(`/usr/bin/time`), Python and its libraries included.

### The ways to the browser, on Tartu

Tartu has 64,828 roads with their 8 level columns. Each call has the same keywords (the level, head and cap columns,
`directed_col`, `driving_col`, `access_col`). The ways are those of
[How a map is drawn](drawing.md#three-choices-for-the-road-data).

| Way | Call | Python | Rust | Peak memory, Python | Peak memory, Rust |
|---|---|---|---|---|---|
| GeoJSON (the default) | `render_edges(edges)` | 19.5 s | 6.1 s | 1.07 GB | 1.64 GB |
| A. Tiles in one HTML file | `render_edges(edges, tiles=True)` | 137.4 s | 13.4 s | 1.33 GB | 1.64 GB |
| B. Tiles on a server, XYZ folder | `export_style(..., format="xyz")` | 152.0 s | 4.6 s | 1.23 GB | 1.06 GB |
| B. Tiles on a server, one PMTiles file | `export_style(..., format="pmtiles")` | 153.5 s | 9.2 s | 1.24 GB | 1.12 GB |
| C. Tiles made in the browser | `new Tiler(...)`, then each tile on request | (none) | see the next table | | 1.05 GB |

For the two pages, the Rust process has the higher peak memory. The plan's columnar road model is the step that cuts the memory
of the engine ([Memory](#memory)).

### Way C: the Tiler and the tiles of one view

Way C exists only with the Rust engine, because the Python engine does not run in a browser. It makes no tile at the start
(`new Tiler`), then each tile on request. A view is the 3 × 3 tiles around the center; each cell gives the time of the 9 tiles,
and the time of the slowest one.

| Area | Where | `new Tiler` | View at zoom 12 | View at zoom 14 | View at zoom 15 |
|---|---|---|---|---|---|
| Tartu (64,828 roads) | natively (the Python binding) | 2.7 s | 0.16 s (slowest 0.07 s) | 0.10 s (0.02 s) | 0.03 s (0.005 s) |
| Monaco (13,298 roads) | natively (the Python binding) | 0.6 s | 0.035 s (0.035 s) | 0.039 s (0.023 s) | 0.037 s (0.010 s) |
| Monaco (13,298 roads) | in the browser (WebAssembly, headless Chromium) | 0.5 s | 0.032 s (0.032 s) | 0.041 s (0.024 s) | 0.036 s (0.011 s) |

The browser numbers are the middle of three runs. The headless browser measures only Monaco, the limit of this machine for a
browser test. On Monaco the WebAssembly module is as fast as the native code.

### In the browser: Rust or MapLibre cuts the tiles

The test compares only stage 2: **the same GeoJSON files go into both cutters, with the same tile settings.**

The input: stage 1 (`makeSources`) made the files of Monaco (13,298 roads with their 8 level columns) one time: `style.json`,
`roads.geojson` (7.75 MB), `simple.geojson` (8.76 MB), `slots.geojson` (0.76 MB) and `road_table.parquet` (1.76 MB).

- **MapLibre** reads the saved `style.json`, with its GeoJSON sources pointing to these files, and cuts the tiles. Its source
  options have stage 2's settings: `maxzoom` 15, `buffer` 10 (stage 2's 80 units of 4,096, on MapLibre's scale of 512) and
  `tolerance` 0.0625 (half a unit of 4,096).
- **Rust** (`tileFiles`) reads the same files and cuts the tiles when MapLibre asks for them.

A map of 1000 × 700 pixels with no base map, headless Chromium, 2026-10-24; the middle value of 3 runs, each in a new page. The
first view is the fair number to compare: both cutters parse the same GeoJSON, MapLibre in the first view and Rust before the map
exists.

| Stage 2 | MapLibre | Rust |
|---|---|---|
| Before the map exists: the data made ready for stage 2 | 0.02 s: the sources only point to the files | 0.51 s: `tileFiles` reads and parses the GeoJSON and indexes the pieces |
| From the start until the whole first view (zoom 14) is drawn, the time above included | 0.98 s: MapLibre reads and parses the GeoJSON, cuts the tiles and draws | 1.09 s: Rust cuts the tiles that MapLibre asks for, and MapLibre draws |
| A zoom to 16 | 0.39 s | 0.37 s |
| A pan | 0.18 s | 0.17 s |
| A zoom out to 12 | 0.21 s | 0.29 s |
| The WebAssembly memory | 158 MB | 316 MB |
| The JavaScript heap | 103 MB | 133 MB |

**The same tiles.** After each view, the test compares the pieces (by road, kind and sort number) and the name and arrow slots
(by road, slot and rank) of the two maps. At zoom 14 they are the same (12,467 and 12,466 pieces; 2,248 slots in both). At the
other views MapLibre has 1 % to 3 % more features in view (zoom 16: 7,994 pieces against 7,786), and every feature of Rust is
also in MapLibre's. The probable cause is a rule of the tiles: roadstyle puts a feature only in the tiles that its box touches,
and uses the buffer only to clip it (the rule of `tiles.py`); MapLibre also puts it in the tiles whose buffer it touches.

**The result: from the same files, the two cutters are about equal.** MapLibre is a little faster at the first view and at zoom
12, and it uses less memory, because Rust must first parse the GeoJSON text into JSON values (the gap "Stage 2 takes the typed
pieces, not JSON" of [Known design gaps](architecture.md#known-design-gaps)).

#### The one call: no files at all

In one call, stage 2 takes stage 1's typed pieces from memory (`tileSources`), and stage 1 writes no files. This path does not
read the files above, so it is not part of the comparison; it shows what the one call gains. The same map and the same views:

| | Rust from memory |
|---|---|
| Stage 1 with no files (with the GeoJSON files: 0.95 s) | 0.29 s |
| Before the map exists: the data made ready for stage 2 | 0.20 s |
| From the start until the whole first view (zoom 14) is drawn | 0.80 s |
| A zoom to 16, a pan, a zoom out to 12 | 0.37 s, 0.19 s, 0.25 s |
| The WebAssembly memory, the JavaScript heap | 83 MB, 79 MB |

It gives the same features as Rust from the files.

The limits of both tests: one area, one machine, software drawing in a headless browser, and no count of the memory of MapLibre's
own workers. An earlier test (2026-10-23) gave Rust half the time of MapLibre for the first view, but it did not give both the same
input or the same tile settings.

### The whole page: Rust's two stages against MapLibre's stage 2

This test compares two real pages, each measured from the start of the page to the whole first view, with the downloads and the
start of the engine included:

- **MapLibre only:** stage 1 was done before. The page downloads its GeoJSON files, MapLibre cuts the tiles (stage 2) and draws.
  The page loads no WebAssembly.
- **Rust, both stages:** the page downloads the roads file (GeoParquet) and the WebAssembly engine; Rust runs stage 1 and stage 2
  in memory (`makeSources`, then `tileSources`), and MapLibre draws.

Monaco (13,298 roads), the same settings as above, a local server, 2026-10-24; the middle value of 3 runs, each in a new browser
context (no cache), after one run to warm the browser.

| | MapLibre only | Rust, both stages |
|---|---|---|
| The download, plain | 17.4 MB: `style.json`, `roads.geojson`, `simple.geojson`, `slots.geojson` | 1.1 MB of roads, and the engine (8.4 MB) |
| The download, gzip | 1.36 MB | 0.93 MB of roads, and the engine (1.93 MB, only on the first visit) |
| The whole first view, from the start of the page | 0.91 s | 1.15 s |
| A zoom to 16 | 0.35 s | 0.36 s |
| A pan | 0.15 s | 0.18 s |
| A zoom out to 12 | 0.18 s | 0.23 s |
| The memory | 100 MB of JavaScript heap, and MapLibre's workers (not measured) | 55 MB of JavaScript heap and 83 MB of WebAssembly |

On Monaco, MapLibre with prepared GeoJSON is a little faster, because the Rust page also runs stage 1 and starts the engine. The
two pages are not the same kind of page, however:

- **MapLibre only** needs stage 1 done before, by a server or a job, for each map, each look and each change of the data.
- **Rust, both stages** needs only the roads. The page can make another look (a palette, a color column, filters) by itself, with
  no server and no new files.

The limits: one area, a local server (no network delay), software drawing in a headless browser, and no count of the memory of
MapLibre's workers.

### Small areas

| Area | What | Python | Rust |
|---|---|---|---|
| Monaco, a part (1,373 roads) | the style of `export_inline` | 0.57 s | 0.12 s |
| Monaco (osmnx, 849 drive edges) | `render_edges` | 0.9 to 1.3 s | 0.3 s |

## Memory

`examples/bench.rs` runs each stage of the Rust engine on Monaco and on Tartu, and gives its time, the peak of the memory in use
during it and the memory in use after it (the bytes that the program has, counted by its allocator):

```bash
cargo run --release --manifest-path rust/Cargo.toml -p roadstyle --example bench
```

Measured on 2026-10-24 on the machine above (other programs ran at the same time, so the times can vary by 20 %):

| Step | Monaco: time | Monaco: peak | Tartu: time | Tartu: peak | Tartu: after |
|---|---|---|---|---|---|
| Read the roads and the base map | 14 ms | 7 MB | 45 ms | 38 MB | 27 MB |
| Stage 1 (`sources_of`) | 93 ms | 20 MB | 378 ms | 99 MB | 73 MB |
| Stage 1 as text (`write_style`, 8.5 MB and 59.1 MB) | 94 ms | 31 MB | 504 ms | 141 MB | 73 MB |
| Stage 2 (`tile_stage`, the tile index) | 114 ms | 29 MB | 641 ms | 168 MB | 152 MB |
| Stage 2's archive (PMTiles, 4.2 MB and 111.4 MB) | 665 ms | 41 MB | 6,396 ms | 596 MB | 152 MB |
| The page (`page_from`, no gzip: 10.3 MB and 67.0 MB) | 494 ms | 69 MB | 2,958 ms | 365 MB | 23 MB |
| The page (`page_from`, gzip: 3.6 MB and 17.8 MB) | 518 ms | 52 MB | 3,835 ms | 253 MB | 23 MB |

Tartu has 64,828 roads; Monaco has 13,298. The archive makes each tile once, with no cache (before 2026-10-24: 7.2 s and 663 MB,
and 68 MB of tiles kept after it). Most of its peak is the PMTiles writer, which keeps every gzipped tile until it writes the
directory.

In the browser, the WebAssembly module used 0.65 to 0.77 times the native peak in earlier measurements. A WebAssembly module has at
most 4 GB, so the engine stops at 200,000 roads (`MAX_ROADS`) with an error. This limit is an estimate from Tartu, not a measurement
of a larger area. Stockholm county (456,813 driving edges) is over the limit.

**See also:** [Architecture of the Rust version](architecture.md) · [Build from source](build.md#run-the-tests)
