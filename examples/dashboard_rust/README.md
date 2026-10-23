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

The page gives `rsDashboard` only the options that the Rust style does not have: `simple` (the one road layer), the selection colour and the
controls.
The road popup fields, the hover tooltip and the hover delay come from the style's metadata `roadstyle:interaction`.
