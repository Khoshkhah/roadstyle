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
| `read` | The roads from GeoParquet (WKB lines), any Parquet table | geolibre-roadstyle `wasm/src/`, commit `eea9f49` (branch `vector-tiles`), then the building heights of `0806ac2` |
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
| `tests/style.rs`, Monaco | The SHA-256 of `make_style` against the style of `0806ac2` from the same inputs, with rule C for the building heights |
| `tests/style.rs`, Tartu (`--ignored`) | The same for Tartu. The inputs (9.5 MB) are not in git. `tests/get_tartu.sh` gets them from the GitHub pre-release `rust-test-data` |
| `tests/levels.rs` | The tags rows and the solve rows of Monaco against duckosm-rust's own `edge_levels_visualization.parquet`, the edge hash and the solve summary |

The reference styles are too large for git (Monaco 26 MB, Tartu 151 MB), so the test keeps only their hashes. To see a difference, make the old style again with `rust/roadstyle-rs/tests/old_style.sh`. It builds `0806ac2` from a geolibre-roadstyle checkout. Then compare the two files.

The test data in `rust/roadstyle-rs/tests/data/`:

| File | Made by |
|---|---|
| `look.json`, `monaco/roads.parquet`, `monaco/features.parquet` | geolibre-roadstyle's fixture (`tools/make_spike_fixture.py`); `look.json` and `features.parquet` from `0806ac2` (`m_per_level` 3.66, the columns `roof_levels`, `min_height`, `min_level`) |
| `tartu/` (from the pre-release, file `tartu-inputs-2.tar`) | The same fixture before `0806ac2`. Its `features.parquet` has the three new columns, but they are empty: the case of a database without these tags |
| `monaco/level_edges.parquet` | The edges and private edges of the three modes from duckosm-rust's test `duckosm-build/tests/levels.rs`, with a `rank` column |
| `monaco/levels_tags.parquet`, `monaco/levels_solve.parquet` | The same duckosm-rust test, as it wrote them (zstd: the tests read zstd, the library does not) |

Result on 2026-10-23: all tests pass, Tartu too. The style of Monaco and the style of Tartu are byte for byte the same as the style of `eea9f49`. After the move, geolibre-roadstyle's `0806ac2` changed the building heights in its copy. The crate has that change too, and its style is byte for byte the same as the style of `0806ac2`. Then Kaveh chose rule C for the building height: the higher of the `height` tag and (`building:levels` + `roof:levels`) x `m_per_level`. In Tartu the `height` tag is often an ETAK code (0 to 9), and levels first makes the buildings of Monaco lower than OpenFreeMap's. With rule C, the style differs from the style of `0806ac2` only in the `height` of 15 buildings of Monaco and 355 of Tartu, and the test has the hashes of the new style. The levels are the same rows as duckosm-rust's.

## Step 3: less memory (2026-10-23)

Kaveh chose to do this step before step 2, because the limit of 100,000 roads stops larger areas, for example Stockholm county. The work is on the branch `rust-memory`. The style and the tiles did not change: the SHA-256 tests of the style and of the tiles (`tests/style.rs`, Monaco and Tartu) give the same hashes as before the step.

Two changes:

1. **The source `roads` takes the roads.** Before, it made a copy of the properties of each road. Now `make_parts` makes it last, after all stages that read the roads, and the properties move into it.
2. **Typed sources `roads` and `simple`** (module `props`). `Props` keeps the properties as a list, with one copy of each key name for the whole program. It has the methods of serde_json's `Map`, so the stages did not change much. A `Feat` keeps its line as numbers, not as JSON arrays. `Source::write_json` writes the same text as the JSON tree, and a unit test compares the two. The layers read typed and JSON properties through the trait `Get`. The base map and the slots stay JSON.

The peak memory, natively (`/usr/bin/time`, the peak resident memory):

| Area | Output | Before | After |
|---|---|---|---|
| Tartu (63,965 roads) | Style | 2.13 GB | 1.13 GB |
| Tartu | Tiles (`make_tiled`) | 2.13 GB | 1.01 GB |
| Monaco (13,298 roads) | Style | 387 MB | 196 MB |

It is also faster: Tartu's style 5.8 s to 5.1 s, Monaco's style 1.1 s to 0.7 s.

`MAX_ROADS` is now 200,000, not 100,000. This number is an estimate, not a measurement. In the earlier measurements, the WebAssembly module used 0.65 to 0.77 times the native peak. Thus Tartu needs about 14 KB for each road, and 200,000 roads need about 2.8 GB of the 4 GB that a browser gives. Before the limit goes higher, measure a larger area in a browser.

What is left: each text value in the properties (colors, classes) is its own string. A value type with one copy of each text would cut more, but the layers read `serde_json::Value`, so that change is larger.

## Step 2: the tiles follow `tiles.py` (2026-10-23)

`make_tiled` and `Tiles` (module `tiles`) now use the rules of roadstyle's `tiles.py`:

| Rule | Before | Now |
|---|---|---|
| Sources | One vector source for each style source | One vector source `roads`. Each old source is a layer in its tiles, and each style layer has that name as its `source-layer` |
| Name and arrow slots | Clipped to the tile | Whole in each tile that they touch, from the first zoom of their layers (14) |
| Zooms and buffer | Zoom 0 to 16, buffer 512 units | `look["config"]["tiles"]`: zoom 6 to 15, buffer 80 units. The look must have these values, else `make_tiled` stops with an error |
| Lines below the last zoom | All points | Simplified to half a tile unit (Douglas-Peucker). A line shorter than half a unit is not in the tile |

The browser API did not change. A page asks for `tile("roads", z, x, y)` and gets all layers in one tile. `props("roads", id)` gives the properties of a road. Polygons are clipped and not simplified, as before. `tiles.py` does not simplify polygons either.

The simplification has no topology check. GEOS's `simplify` (with `preserve_topology`) also keeps a line from crossing itself.

Sizes and times natively (`main.rs --tiles`, the tiles around the center):

| Area, zoom | Before | Now |
|---|---|---|
| Monaco, 12 | 2.8 MB, 575 ms a tile | 2.7 MB, 222 ms a tile |
| Tartu, 12 | 26.4 MB | 16.8 MB |
| Tartu, 14 | 26.5 MB | 18.1 MB |
| Tartu, last zoom (16 before, 15 now) | 29.0 MB in 1,008 tiles | 18.8 MB in 313 tiles |

## Next steps

1. geolibre-roadstyle and duckosm-rust use the crate at a fixed commit and delete their copies. The duckosm-rust session does this step.
2. The tiles follow `tiles.py`: done (see above). duckosm-rust's page must show the map again with the new tiles.
3. Typed pieces in place of JSON trees, to use less memory: done (see above).
4. The Python binding. Then Python roadstyle calls Rust part by part, and its golden tests check each part.
