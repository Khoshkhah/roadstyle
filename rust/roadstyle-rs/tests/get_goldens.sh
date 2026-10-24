#!/usr/bin/env bash
# Get the large goldens of the Rust tests (tests/areas.rs, tests/style.rs) from the GitHub pre-release rust-test-data into tests/data/
# (not in git): the styles and tiles of Monaco and Södermalm, and Tartu's inputs and goldens. tests/make_goldens.py makes them.
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)/data"
tar="$dir/goldens-2.tar"
curl -fsSL -o "$tar" https://github.com/Khoshkhah/roadstyle/releases/download/rust-test-data/goldens-2.tar
echo "b13ac86721d0f0cf9344ab5cda572f80b228d9bcae21489c22564db4428b25bf  $tar" | sha256sum -c -
tar -xf "$tar" -C "$dir" && rm "$tar"
