"""Writes the old paths that duckosm-rust's page build copies (crates/duckosm-wasm/build.sh, at a roadstyle commit) from their one
source, rust/roadstyle-assets/files/static/: src/roadstyle/static/popup.css, popup.js, level_editor.html and dashboard/ (with its
subfolders). The copies are exact, so the files that duckosm-rust serves do not change. Do not edit them: edit the source and run
this script; tests/test_release_files.py fails when a copy differs. They go in roadstyle 0.27.0, after duckosm-rust takes the new
paths (T6).

    python rust/roadstyle-assets/sync_old_paths.py
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "rust" / "roadstyle-assets" / "files" / "static"
OLD = ROOT / "src" / "roadstyle" / "static"
PATHS = ["popup.css", "popup.js", "level_editor.html", "dashboard"]


def pairs():
    """(source, copy) for each file of the old paths."""
    for p in PATHS:
        src = SOURCE / p
        for f in sorted(src.rglob("*")) if src.is_dir() else [src]:
            if f.is_file():
                yield f, OLD / f.relative_to(SOURCE)


if __name__ == "__main__":
    shutil.rmtree(OLD / "dashboard", ignore_errors=True)        # a file that left the source leaves the copy
    for src, dst in pairs():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    print(f"{sum(1 for _ in pairs())} files copied to {OLD.relative_to(ROOT)}")
