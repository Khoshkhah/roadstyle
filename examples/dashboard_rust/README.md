# Dashboard on a Rust-engine style

This page shows roadstyle's dashboard modules (`src/roadstyle/static/dashboard/`) on a style that the Rust engine makes.
The engine is `rust/roadstyle-wasm`. The data is the Monaco test data in `rust/roadstyle-rs/tests/data/`.

## Build the WebAssembly module

Run these commands in the root of the repository:

```bash
CARGO_BUILD_JOBS=4 cargo build --release --target wasm32-unknown-unknown --manifest-path rust/Cargo.toml -p roadstyle-wasm
```

```bash
wasm-bindgen --target web --out-dir examples/dashboard_rust/pkg rust/target/wasm32-unknown-unknown/release/roadstyle_wasm.wasm
```

Git ignores the `pkg/` folder.

## Open the page

Serve the root of the repository, because the page reads the modules and the data from there:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/examples/dashboard_rust/`.

The look's `args.levels` is the value that `roads_sql.js` `makeRoads` returns for a duckOSM file with stored levels: the engine checks
that the levels in `roads.parquet` were solved for these edges. With `"tags"`, the engine computes the levels from the tags.

The page gives `rsDashboard` only what the Rust style does not have: the road table (`makeSources(...).roadTable()`), the selection
colour and the controls.
The road popup fields, the hover tooltip and the hover delay come from the style's metadata `roadstyle:interaction`.
The page colours the roads by their lane count (`color_by="lanes"` in the look's `args`). The legend comes from the style's metadata
`roadstyle:color_options`.

## The tile example

`tiles.html` adds the roads later, as vector tiles of the engine's `Tiler`, on an OpenFreeMap base map. It uses the dashboard
as duckosm-rust's page does: `style: null` and `prefix: "rs-"` at the start, `rs.setStyle(style)` after the roads are on the map,
and the road table of each style (`rs.setStyle(style, {road_table})`). The button replaces the roads style with another colouring.
Open `http://localhost:8000/examples/dashboard_rust/tiles.html`. It needs the internet for MapLibre and the base map.
