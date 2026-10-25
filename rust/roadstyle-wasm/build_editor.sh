#!/usr/bin/env bash
# The WebAssembly package of the Rust level editor (${CARGO_TARGET_DIR:-rust/target}/editor-pkg/, a build output, not in git):
# roadstyle-levels edit and roadstyle serve give the page that loads it (roadstyle-serve's build.rs builds this folder in, at
# level_editor/pkg/). Run from anywhere, before the build of the program or the Python extension; needs the target
# wasm32-unknown-unknown and wasm-bindgen.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
target="${CARGO_TARGET_DIR:-$root/rust/target}"
CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-4}" cargo build --profile dist --offline --target wasm32-unknown-unknown --manifest-path "$root/rust/Cargo.toml" -p roadstyle-wasm
wasm-bindgen --target web --out-dir "$target/editor-pkg" "$target/wasm32-unknown-unknown/dist/roadstyle_wasm.wasm"
echo "$target/editor-pkg/ built"
