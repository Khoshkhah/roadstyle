# R10: the base map and the overlays as a typed FeatureTable (plan; steps 1, 2 and 6 done)

Audit R10 (audit_2026-10-23.md; refined by N5 of audit_2026-10-24.md): the base map and the overlays go through the engine as
`serde_json` trees. This note gives the plan for the base map's and the overlays' part of R10. The slots and the 3D decks stay with
roadstyle-rs. The code starts after roadstyle-rs's stack (R14 changes the tile code now) is on rust-engine.

## Today, measured on Tartu (2026-10-24)

Tartu's inputs of tests/get_goldens.sh, the look of tests/data/look.json with the names and the arrows, an export (`export: true`), the
native release build, one process for each run (peak resident memory from `/usr/bin/time`).

| | Roads only | With the base map | The base map's part |
|---|---|---|---|
| Peak memory | 309 MB | 481 MB | 172 MB |
| Stage 1 (make_sources) | 743 ms | 871 ms | 128 ms |
| Stage 2 (tile_made) | 1,177 ms | 1,499 ms | 322 ms |
| Tiles at z12, z14 and z15 (each tile of the box) | 192 tiles, 549 ms | 582 tiles, 811 ms | 262 ms (and 390 more tiles) |

The base map has 31,788 features (28,549 polygons, 2,617 points, 617 lines, 5 multipolygons) with 275,531 points. Its rows are
7.5 MB as Arrow columns; its sources are 13.2 MB of GeoJSON text. In the engine they are JSON trees: the bench of the facade program
(`roadstyle-rs --bench`) measures 107 MB more in use after the base-map step. A typed table needs about 4.4 MB for the points (one
buffer of `[f64; 2]`) and about 3 MB for the columns.

## Where the trees are made and read

| Place | What it does with JSON | Owner |
|---|---|---|
| roadstyle-io `read::read_table` | each Parquet row as a `Row` (a JSON `Map` with its column names, the geometry as WKB bytes) | look session |
| roadstyle-io `duckosm::cut_sea` | the background's WKB, as GeoJSON and back to WKB | look session |
| roadstyle-engine `features.rs` (`feature_collections`) | each row as a GeoJSON feature in a FeatureCollection for each layer (heights, base, area order) | R10: look session |
| roadstyle-engine `overlays.rs` (77 `Value` uses) | `Overlay.fc` (the data), `edge_attach` (`edge_id` into each feature's properties), `feature_overlays`, `user_overlays` (the args' GeoJSON), `item_pieces`, `road_items`, `edge_overlay` | R10: look session |
| roadstyle-engine `sources.rs`, `Src::Json` (15 places) | a base-map or overlay source is a JSON tree; `write_data` writes it as text | roadstyle-rs |
| roadstyle-engine `palettes.rs` | a property of a JSON source that differs in a view's palette gets its copy | roadstyle-rs |
| roadstyle-tiles `Tiles::add` | parses the GeoJSON features back into geometry and properties | R10: look session (the feature input only) |
| facade `write_source_file`, roadstyle-io `write::parquet_to` | a JSON source to GeoParquet, through a JSON value for each cell (N5) | roadstyle-rs |

## The plan

1. **The type** (roadstyle-model, as the plan's crate table says: "RoadTable and FeatureTable"). `FeatureTable`: the property
   columns as Arrow arrays (the readable types of `RoadTable`), one coordinate buffer `Vec<[f64; 2]>`, and the offsets of each
   feature's parts and rings with its geometry type (Point, LineString, Polygon and the Multi types; the form of GeoArrow's offsets).
   A `Feature` view (as `Road`) gives a feature's properties (`Cell`) and its geometry (slices of the buffer). With it: `from_wkb`
   (a WKB column) and `from_geojson` (a FeatureCollection value, for the overlays of the args), and `filter`/`take` by row. This is
   roadstyle-rs's crate: I propose the type as one small change, reviewed first (rule 2 of the parallel work), or roadstyle-rs adds it.
2. **The reader** (roadstyle-io, mine): `read_features(bytes) -> FeatureTable` straight from the Parquet columns and the WKB
   column; `cut_sea` on the table's buffer (no WKB and no GeoJSON in between).
3. **The base map** (`features.rs`): one `FeatureTable` for each layer of layers.yaml, the heights and the base as Float64 columns,
   the polygons in the order of their area (largest first), with no GeoJSON feature made.
4. **The overlays** (`overlays.rs`): `Overlay.fc` becomes a `FeatureTable`; `edge_attach` adds an `edge_id` column (the R-tree of
   the roads stays); `feature_overlays`, `user_overlays` (from `FeatureTable::from_geojson` of the args), `item_pieces`, `road_items`
   and `edge_overlay` read the table. The layers that the overlays make do not change.
5. **The sources and the writers** (roadstyle-rs's files, a call site each): a source `Src::Features(FeatureTable)` beside `Src::Json`,
   written as GeoJSON text a feature at a time (as `RoadsSource::write_json`) and as GeoParquet from its Arrow columns (as N5 does for
   the roads). The view palettes (`palettes.rs`) give a typed source its copies as more columns.
6. **The tiles' feature input** (roadstyle-tiles): `Tiles::add_features(name, &FeatureTable, keep, whole, min_zoom)` reads the buffer
   and the columns; `Tiles::add` of JSON stays for the sources that remain JSON (the slots, the decks, until roadstyle-rs types them).

## The landing order

Each step is its own commit, with every golden equal (tests/style.rs's hashes, tests/sources.rs, tests/stages.rs, the mapstyle digests
of tests/test_duckosm.py, the Python parity tests) and its measured numbers on Tartu.

1. Step 1 (the type) and step 2 (the reader), with the tests of the type (WKB and GeoJSON to the table and back).
2. Step 3 (the base map) with step 5's typed source and its GeoJSON writer: the first step that changes the memory.
3. Step 6 (the tiles' input), then the GeoParquet writer of step 5.
4. Step 4 (the overlays of the args: `user_overlays`, the items).
5. Remove the JSON path of the base map (`Row` for features, `Tiles::add` for a base-map source).

Expected: the base map's memory falls from 172 MB to about 10 MB on Tartu (measured after each step), and stage 2 needs no GeoJSON
parse for the base map.

## Step 2, done (2026-10-24)

The reader, the sea cut, the base map and the typed source in one step (landing steps 1 and 2 of the plan): the facade's
`read_features` gives a `FeatureTable` (`read::read_feature_table`), `duckosm::cut_sea` cuts the sea out of the table's buffer,
`features::feature_tables` makes one table for each layer, `overlays::edge_attach` and `edge_overlay` add their columns to the table,
and the source `Src::Features` writes the table as GeoJSON. A caller's overlays stay JSON (`overlays::Data::Json`). Stage 2's tiles and
the GeoParquet writer still read a typed source through one JSON value of it (steps 5 and 6).

Two rules of the table keep the bytes of today's GeoJSON: a column writes its nulls or leaves the key out (`"name": null`, but no
`bearing` key when there is no bearing), and a column of numbers knows its integers (mapstyle's heights: `6` from the kind's table,
`9.0` from a tag; 763 of Monaco's heights are integers, 499 are floats).

Tartu, the same method as above, rust-engine at e9e57e0 against this step (each the middle of three runs):

| | rust-engine | Step 2 |
|---|---|---|
| Stage 1 (`--sources`), peak memory with the base map | 403 MB | 284 MB |
| The base map's part of it (roads only: 274 MB) | 129 MB | 10 MB |
| make_sources, the base map's part (less the same build's run of the roads only) | 115 ms | 58 ms |
| make_tiled, peak memory with the base map (roads only: 311 MB) | 483 MB | 351 MB |
| make_tiled, time with the base map | 2,074 ms | 2,060 ms |

The files of stage 1 (GeoJSON and GeoParquet, 22 files) and every golden are the same bytes. Stage 2 keeps 40 MB for the base map: the
JSON value of each typed source for `Tiles::add`, which step 6 removes.

## Step 6, done (2026-10-24)

`Tiles::add_features` cuts a typed source into tiles from its table: the same ids (the row), the same properties (the keys of each
GeoJSON feature, `FeatureTable::has_key`) and the same geometries as `Tiles::add` of its GeoJSON, with no JSON value between. The
tiles of Monaco and Tartu are the same bytes (tests/style.rs, tests/stages.rs). Tartu, make_tiled with the base map (roads only: 311 MB,
1,690 ms):

| | Step 2 | Step 6 |
|---|---|---|
| Peak memory | 351 MB | 344 MB |
| Time | 2,060 ms | 1,752 ms |

The base map's 33 MB that stay are its tile layers (each feature's geometry in Web Mercator and its value numbers).

