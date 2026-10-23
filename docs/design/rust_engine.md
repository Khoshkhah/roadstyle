# One Rust engine for roadstyle

Status: step 1 is done (2026-10-23). The crate is in `rust/`. The Python code of roadstyle did not change.

## Why

Before this step, the style engine had three copies. Python roadstyle is the reference. geolibre-roadstyle has a Rust port in `wasm/` (the GeoLibre plugin and the browser page of duckosm-rust). duckosm-rust has a Rust port of roadstyle's level solver. The copies already differ. For example, the `roads_sql.js` file of duckosm-rust and the file of geolibre-roadstyle differ in 33 lines.

The plan has one Rust crate in this repository with three front-ends: WebAssembly, native Rust and a Python binding. Python roadstyle keeps its API and its folium and lonboard drawing. Later, it calls Rust for the heavy parts.

## What is in the crate

`rust/` is a cargo workspace with two members:

| Member | Type | Content |
|---|---|---|
| `roadstyle-rs` | library and native program | The engine and `src/main.rs` (the native front-end) |
| `roadstyle-wasm` | `cdylib` | The browser front-end: `makeStyle`, `Tiler` and `memoryBytes` through wasm-bindgen, and the `grow` allocator. Natively the crate is empty. |

The modules of `roadstyle-rs`, and where they come from:

| Module | Content | From |
|---|---|---|
| `read` | The roads from GeoParquet (WKB lines), any Parquet table | geolibre-roadstyle `wasm/src/`, commit `eea9f49` (branch `vector-tiles`) |
| `roads`, `simple`, `slots` | The `roads` source, the casing pieces, the names and arrows | the same |
| `features`, `overlays`, `geom` | The base-map layers, `edge_attach`, WKB, GEOS's area and centroid | the same |
| `layers` | The road tables, the expression builders and the passes on the layer list | the same |
| `planner` | `metadata["roadstyle:planner"]` | the same |
| `tiles` | The vector tiles on request (`Tiles`, `props`) | the same |
| `levels` | roadstyle's `compute_levels`: the tags rule, and the solver (least span first, then a push-relabel min-cost flow) | duckosm-rust `crates/duckosm-core/src/levels/`, commit `60dbede` (branch `browser-b4`) |

The code moved without changes, with two exceptions:

- `levels` has its own input type, `LevelEdge`: `edge_id`, `highway`, `tunnel`, `bridge`, `layer`, `junction` and the line. In duckosm-core, the solver read `Edge` and `Mode`. Now the caller gives each edge a rank (`LevelEdges::add(rank, edge)`), and the edge with the lowest rank wins. duckOSM's ranks are: driving 0, walking 1, cycling 2, then their private edges 3, 4 and 5. Thus the crate does not depend on duckosm-core.
- The `lib.rs` of the engine has no wasm code. The allocator and the wasm-bindgen API are in `roadstyle-wasm`.

The Python binding (maturin and PyO3) will be a third member, `roadstyle-py`. It is not in this step.

## Tests

```bash
cd rust
cargo test --offline
```

| Test | What it compares |
|---|---|
| The unit tests of both ports (11) | The flow, the solver, the input geometry, the tiles |
| `tests/style.rs`, Monaco | The SHA-256 of `make_style` against the style of `eea9f49` from the same inputs |
| `tests/style.rs`, Tartu (`--ignored`) | The same for Tartu. The inputs (9.5 MB) are not in git. `tests/get_tartu.sh` gets them from the GitHub pre-release `rust-test-data` |
| `tests/levels.rs` | The tags rows and the solve rows of Monaco against duckosm-rust's own `edge_levels_visualization.parquet`, the edge hash and the solve summary |

The reference styles are too large for git (Monaco 26 MB, Tartu 151 MB), so the test keeps only their hashes. To see a difference, make the old style again with `rust/roadstyle-rs/tests/old_style.sh`. It builds `eea9f49` from a geolibre-roadstyle checkout. Then compare the two files.

The test data in `rust/roadstyle-rs/tests/data/`:

| File | Made by |
|---|---|
| `look.json`, `monaco/roads.parquet`, `monaco/features.parquet` | geolibre-roadstyle's fixture (`tools/make_spike_fixture.py`) |
| `monaco/level_edges.parquet` | The edges and private edges of the three modes from duckosm-rust's test `duckosm-build/tests/levels.rs`, with a `rank` column |
| `monaco/levels_tags.parquet`, `monaco/levels_solve.parquet` | The same duckosm-rust test, as it wrote them (zstd: the tests read zstd, the library does not) |

Result on 2026-10-23: all tests pass, Tartu too. The style of Monaco and the style of Tartu are byte for byte the same as the style of `eea9f49`. The levels are the same rows as duckosm-rust's.

## Next steps

1. geolibre-roadstyle and duckosm-rust use the crate at a fixed commit and delete their copies. The duckosm-rust session does this step.
2. The tiles follow `tiles.py`:
   - one source `roads` with source layers;
   - `slots` whole, not clipped;
   - the zooms and the buffer from `look["config"]["tiles"]` (zooms 6 to 15, buffer 80);
   - at low zooms, simplification to half a tile unit.
3. Typed pieces in place of JSON trees, to use less memory. Tartu needs 2.1 GB natively. Because of this, the limit is 100,000 roads.
4. The Python binding. Then Python roadstyle calls Rust part by part, and its golden tests check each part.
