#!/usr/bin/env bash
# Get the inputs of the Tartu test (tests/style.rs) from the GitHub pre-release rust-test-data into tests/data/tartu/ (not in git).
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)/data/tartu"
mkdir -p "$dir"
curl -fsSL -o "$dir/tartu-inputs.tar" https://github.com/Khoshkhah/roadstyle/releases/download/rust-test-data/tartu-inputs-2.tar
echo "b31144eb9c3598ffaef2445495b2890c0ec60122518884e25e70d535f156b2a5  $dir/tartu-inputs.tar" | sha256sum -c -
tar -xf "$dir/tartu-inputs.tar" -C "$dir" && rm "$dir/tartu-inputs.tar"
