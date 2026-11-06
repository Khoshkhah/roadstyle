#!/usr/bin/env bash
# The checks that fail CI most often, in about a minute: run it before `git push` (Kaveh, 2026-11-06: a full CI run takes 25 minutes, and
# three faults of one day were a lint error, a comment that named Python and old copies of the dashboard files).
#   scripts/check.sh            lint, the guard of the Rust crates, the old-path copies, the manual, and the test files that this branch changed
#   PYTHON=<python> scripts/check.sh    the Python of the environment that has roadstyle (default: python)
# The extension must be built for the test files (python rust/roadstyle-py/build.py); the first four checks need no build.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"

echo "== ruff"
"$PY" -m ruff check src tests
echo "== no Python design in the Rust crates"
python3 scripts/check_no_python_shape.py
echo "== the old-path copies of the assets"
"$PY" rust/roadstyle-assets/sync_old_paths.py >/dev/null
if ! git diff --quiet -- src/roadstyle/static; then
  echo "sync_old_paths.py changed src/roadstyle/static: commit these copies"; git diff --stat -- src/roadstyle/static; exit 1
fi
# the test files that this branch changed or added (against origin/main), and the two tests that check the files and the manual
base=$(git merge-base HEAD origin/main 2>/dev/null || echo HEAD)
changed=$( { git diff --name-only "$base" -- 'tests/test_*.py'; git ls-files --others --exclude-standard -- 'tests/test_*.py'; } | sort -u | while read -r f; do [ -f "$f" ] && echo "$f"; done)
echo "== pytest: the files and the manual${changed:+, and }$(echo $changed | tr ' ' ',')"
"$PY" -m pytest -q -p no:cacheprovider tests/test_release_files.py tests/test_dashboard_manual.py $changed
