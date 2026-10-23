#!/usr/bin/env bash
# Get the inputs of the Tartu test (tests/style.rs) from the GitHub pre-release rust-test-data into tests/data/tartu/ (not in git).
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)/data/tartu"
mkdir -p "$dir"
curl -fsSL -o "$dir/tartu-inputs.tar" https://github.com/Khoshkhah/roadstyle/releases/download/rust-test-data/tartu-inputs.tar
echo "87324e85a0cc7ba025530f270b19e2269d8955cb10c09821f5b119e34304e6a6  $dir/tartu-inputs.tar" | sha256sum -c -
tar -xf "$dir/tartu-inputs.tar" -C "$dir" && rm "$dir/tartu-inputs.tar"
