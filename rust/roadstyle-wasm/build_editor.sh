#!/usr/bin/env bash
# The WebAssembly package of the Rust level editor (src/roadstyle/static/level_editor/pkg/, not in git): roadstyle-levels edit and
# roadstyle serve give the page that loads it. Run from anywhere; needs the target wasm32-unknown-unknown and wasm-bindgen.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-4}" cargo build --profile dist --offline --target wasm32-unknown-unknown --manifest-path "$root/rust/Cargo.toml" -p roadstyle-wasm
wasm-bindgen --target web --out-dir "$root/src/roadstyle/static/level_editor/pkg" "$root/rust/target/wasm32-unknown-unknown/dist/roadstyle_wasm.wasm"
echo "src/roadstyle/static/level_editor/pkg/ built"
