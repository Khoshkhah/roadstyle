# Parity and speed

<p class="lead">About how the tests show that the Rust engine makes the same output as the Python engine, how fast it is, and how
much memory it uses.</p>

## What "the same" means

For the style and the page, the same means byte for byte: the same keys in the same order, the same numbers to the last digit.
The Rust engine writes JSON as Python's `json.dumps` writes it, with its separators, its `\uXXXX` escapes and its floats
(`1e-05`, `60.0`), and it parses floats exactly.

For the tiles, the same means the same features when decoded: the same ids, properties and geometry. The bytes can differ,
because Python's encoder (`mapbox_vector_tile`) writes a negative integer as `int_value` and a float with no fraction as an
integer, and the engine writes `sint_value` and a double. MapLibre reads the same numbers from both.

## The goldens

`rust/roadstyle-rs/tests/make_goldens.py` is the one generator of the reference outputs. It runs Python roadstyle on three areas:

| Area | Roads | Goldens |
|---|---|---|
| Monaco | 13,298 | the style of `export_inline`, the tiles of `export_style`, the levels (tags and solve), the color cases, the looks |
| Södermalm (sample) | 4,563 driving edges | the style, the tiles, the levels, with duckOSM's solved levels |
| Tartu | 64,828 | the style, the tiles, the levels of the tags rule |

The tiles are the 3 × 3 tiles around the center at zooms 12, 14 and 15. The files over 1 MB and Tartu's inputs are on the
GitHub pre-release `rust-test-data`. The repository keeps their SHA-256, and `get_goldens.sh` checks it.

The Rust tests (`cargo test`) compare the engine with the goldens: `areas.rs` for the three areas, `colors.rs` for the
data-driven color, `look.rs` for the looks of each profile and palette, `levels.rs` and `style.rs`.

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

The same roads and the same look go to the browser in two ways. **MapLibre:** `makeStyle` gives the style with GeoJSON sources,
and MapLibre cuts the tiles itself. **Rust:** `new Tiler` gives the style with a vector source, and `tiler.tile()` cuts each tile
when MapLibre asks for it. Both include stage 1. Monaco (13,298 roads, with their 8 level columns), a map of 1000 × 700 pixels
with no base map, headless Chromium; the middle value of 3 runs, each in a new page.

| Step | MapLibre cuts the GeoJSON | Rust cuts the tiles |
|---|---|---|
| The engine (stage 1; for Rust also the tile index) | 0.65 s (`makeStyle`) | 0.65 s (`new Tiler`) |
| The size of the style that MapLibre gets | 23.2 MB, with the GeoJSON | 0.09 MB, only the rules |
| The first complete view, zoom 14 (MapLibre's `idle` event) | 1.16 s | 0.56 s |
| A zoom to 16 | 0.49 s | 0.35 s |
| A pan | 0.36 s | 0.21 s |
| A zoom out to 12 | 0.25 s | 0.25 s |
| The JavaScript heap of the page | 112 MB | 82 MB |

With the Rust `Tiler`, the first view comes in half the time, and the zoom and the pan are faster. With GeoJSON, MapLibre first
takes a 23 MB style and cuts all the roads; with the `Tiler` it gets only the rules and asks for the tiles in view. The test has
limits: one area, one machine, software drawing in a headless browser, and no count of the memory of MapLibre's own workers.

### Small areas

| Area | What | Python | Rust |
|---|---|---|---|
| Monaco, a part (1,373 roads) | the style of `export_inline` | 0.57 s | 0.12 s |
| Monaco (osmnx, 849 drive edges) | `render_edges` | 0.9 to 1.3 s | 0.3 s |

## Memory

The peak resident memory of the native program (`/usr/bin/time`), for the style:

| Area | Roads | Peak | Time |
|---|---|---|---|
| Monaco | 13,298 | 194 MB | 0.55 s |
| Tartu | 64,828 | 1.13 GB | 2.9 s |

Tartu uses about 17 KB for each road. In the browser, the WebAssembly module used 0.65 to 0.77 times the native peak in earlier
measurements. A WebAssembly module has at most 4 GB, so the engine stops at 200,000 roads (`MAX_ROADS`) with an error. This
limit is an estimate from Tartu, not a measurement of a larger area. Stockholm county (456,813 driving edges) is over the limit.

The memory for each road goes down when the columnar road model of the plan is built (P4). It is not built.

**See also:** [Architecture of the Rust version](architecture.md) · [Build from source](build.md#run-the-tests)
