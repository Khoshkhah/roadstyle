#!/usr/bin/env bash
# Make the reference style of tests/style.rs: the style of geolibre-roadstyle's Rust port at commit 0806ac2, from the same inputs.
# Usage: old_style.sh <geolibre-roadstyle checkout> <area folder with roads.parquet and features.parquet> <out.json>
# Its building heights follow rule A; the crate's follow rule C, so only the `height` of some buildings differs (tests/style.rs).
set -euo pipefail
repo=$1; area=$2; out=$3
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git -C "$repo" archive 0806ac2 wasm | tar -x -C "$tmp"
cargo run --offline --release --quiet --manifest-path "$tmp/wasm/Cargo.toml" -- \
    "$here/data/look.json" "$area/roads.parquet" "$area/features.parquet" - "$out"
sha256sum "$out"
