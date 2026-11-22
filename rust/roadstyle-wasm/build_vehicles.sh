#!/usr/bin/env bash
# roadstyle's vehicles module (rs.vehicles, docs/design/vehicles_spec.md): roadstyle-wasm with the feature "vehicles", in the Python package
# at src/roadstyle/static/vehicles/pkg/ (a build output, not in git): roadstyle_wasm.js and roadstyle_wasm_bg.wasm.gz (gzip: 3.7 MB, not
# 14 MB; the page decompresses it). render_edges(..., vehicles=...) puts it in the page. The release workflow runs this before the wheels.
# Run from anywhere; needs the target wasm32-unknown-unknown and the wasm-bindgen program of the version in rust/Cargo.lock.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
target="${CARGO_TARGET_DIR:-$root/rust/target}"
out="$root/src/roadstyle/static/vehicles/pkg"
CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-4}" cargo build --profile dist --offline --target wasm32-unknown-unknown --manifest-path "$root/rust/Cargo.toml" -p roadstyle-wasm --features vehicles
rm -rf "$out" "$target/vehicles-pkg"
wasm-bindgen --target web --no-typescript --out-dir "$target/vehicles-pkg" "$target/wasm32-unknown-unknown/dist/roadstyle_wasm.wasm"
mkdir -p "$out"
cp "$target/vehicles-pkg/roadstyle_wasm.js" "$out/"
gzip -9cn "$target/vehicles-pkg/roadstyle_wasm_bg.wasm" > "$out/roadstyle_wasm_bg.wasm.gz"
ls -l "$out"
