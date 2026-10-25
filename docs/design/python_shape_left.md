# The Python shape that is still in the Rust side

A read-only list (2026-10-24, at `d065db9`: rust-engine `efc7912` with D3, N29, D9 and the Rust-made goldens) for the target
architecture document. The rule of 2026-10-24 is that the Rust API is the design and Python is a thin binding (rust_library.md, the
decisions). Each kind below is Python's design that the Rust side still copies. The counts are of the code in `rust/*/src/`, not of
the tests. The last column names the held item that removes it.

## The summary

| Kind | Where (the most) | Count | Removed by |
|---|---|---|---|
| Map options as `Value` with Python's keyword names | `roadstyle-engine/src/lib.rs` (25), `contract.rs` (11), `layers.rs` (7), `roads.rs` (4), the facade, the look | 87 reads of `args["…"]`, 44 names; `page_options.rs` reads about 25 more through `a["…"]` | N32 (typed `MapOptions` with defaults; an unknown key is an error) |
| Python's truth of a JSON value | `layers.rs:369` `py_truth`, `roads.rs:105` and `look/src/lib.rs:140`, `resolve.rs:199`, `level_area.rs:254` `truthy` | 5 definitions, 65 calls | N32 (a typed option has one type: no truth of "", 0 or "no") |
| `"__rs_*"` property keys as strings | `layers.rs` (52), `simple.rs` (47), `draw.rs` (42), `overlays.rs` (21), `slots.rs` (16), `decks.rs` (11) | 273 literals, 59 names | N30 + R6 (one table of the names, or a typed property enum) |
| The renames of the user's columns (`ColumnMap`) | `roadstyle-engine/src/lib.rs:342` (`to_engine` at the input, `to_user` on every output source and layer) | 1 type, 2 passes over all output | N30 + R6 (the engine reads the user's columns by the options; the binding renames at its border if Python needs the old names) |
| Files that the crates read from `src/roadstyle/` | `roadstyle-look/src/basemap.rs` (24), `resolve.rs` (9), `page.rs` (9 and the dashboard modules of `files.txt` through `build.rs`), `page_options.rs` (3), `ramp.rs`, `props.rs`, the CLI (2) | 47 `include_str!`/`include_bytes!`/`asset!`, and the dashboard bundle | N25 (P7's packaging: the crates' own copy, or one data crate) |
| Python's rounding and number text | `look/src/widths.rs:9` `py_round` (35 calls), `basemap.rs:93` `py_round`, `slots.rs:44` `py_divmod`, `colors.rs:43` `py_str`, `roads.rs:119` `py_float`, `resolve.rs:351` `py_num`, `page_options.rs:190` `repr` (9 calls, for Python's error text) | 7 helpers | P7 (after Rust is the reference: Rust's own rounding; the error text in Rust's form) |
| Facade entries named after Python functions | `make_style` (export_inline), `make_sources` / `save_sources` / `file_names` / `source_file` (export_geojson), `tile_files` / `tile_files_with` (tile_geojson), `make_tiled` / `tiled_of` / `tile_made` / `tile_stage` (render(tiles=True), export_style), `page_defaults` (render's signature), `sidebar_defaults` (pages.py), `make_page` (`_page_html`'s JSON parts) | 24 public functions in the facade; 5 for stage 2 | N24 (the two stages and the typed options) with N21 + D7 (one stage-2 call) |
| Options that only Python's paths set | `lib.rs:407-408` `tile_keep` and `tile_layers` (no caller sets them: dead), `lib.rs:115` the `simple=False` refusal, `contract.rs:93` the full look's roles (`casings`, `halves`, `ends`), `contract.rs:127` the full look's pick rule, `contract.rs:167` `fill_layers: []`, `page.rs:39` `simple: false`, the error texts that name `engine='python'` (`page_options.rs:103`, `lib.rs:117`) | 2 dead options, 6 full-look places | N21 (`tile_keep`/`tile_layers`) and N16 / P7 (the full look goes with Python's engine) |
| JSON shapes that exist for Python's page | the road table as `tiles.sidecar`'s form `{props, mids, bboxes, lines}` (`lib.rs:343`), `RS_SIMPLE`'s settings (`page_options.rs:168`), the gzip blob map `rs-gz` and `rs-side` (`page.rs:228-237`), `make_page`'s JSON `parts` (`page.rs:244`) | 4 shapes | N24 (make_page goes: page_from is the one call); the road table's form with D11 (its writer) under the architecture document |
| The bindings' own composition | Python: `make_style`, `Tiler::new` (make_tiled), `Sources.tile_stage` (its own TileOptions), `make_sources`, `page_from`, `make_page`; wasm: `makeStyle`, `makeSources`, `tileSources`, `tileFiles`, `makePage`; the two `duckosm_plan`s take other JSON keys | Python 6, wasm 5 stage calls, 2 plan shapes | N21 + D7 (one stage-2 call in Rust, Python and JS; one `duckosm::plan`) |
| Comments that name Python code as the reference | `render_web.`, `_engine.`, `tiles.py`, `export.py`, "Python's", … in `roadstyle-engine` (64), the facade (29), `roadstyle-tiles` (19), `roadstyle-look` (12), `roadstyle-model` (9), `roadstyle-io` (6) | 139 | each item above, as it rewrites its code; the rest at P7 |

## Notes

- The counts of `args` include only the reads by a fixed name. The look's parts (`theme`, `config`, `styles`, `roads_model`) are
  `Value` too: the look session's typed look (R16, R17) covers them, and N32 step 1 (typed `Args`) is the look session's.
- `py_round` is in `roadstyle-look`; its 35 calls give the widths and the offsets the numbers of Python's `round`. With byte parity no
  longer a goal, it can become Rust's rounding at once, but every style hash changes, so it waits for P7 as rust_library.md says.
- The CLI's two `include_str!` (MapLibre) are the program's own offline page, not Python's shape; they are counted under N25 because
  they read `src/roadstyle/vendor/`.
- Gone already on 2026-10-24: `pyjson` (Python's `json.dumps` in Rust; D3, N29), the Python goldens of every Rust test (N27, D5 and
  the levels session), `as_decided`.
