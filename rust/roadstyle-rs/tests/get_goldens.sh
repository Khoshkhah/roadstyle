#!/usr/bin/env bash
# Get the large goldens of the Rust tests (tests/areas.rs, tests/style.rs) from the GitHub pre-release rust-test-data into tests/data/
# (not in git): the styles and tiles of Monaco and Södermalm, and Tartu's inputs and goldens. tests/make_goldens.py makes them.
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)/data"
tar="$dir/goldens-1.tar"
curl -fsSL -o "$tar" https://github.com/Khoshkhah/roadstyle/releases/download/rust-test-data/goldens-1.tar
echo "f98c38fe2cbc99d0f4c1a7f549ca16e79d0ae314409b180ee1242a007a15f4fe  $tar" | sha256sum -c -
tar -xf "$tar" -C "$dir" && rm "$tar"
