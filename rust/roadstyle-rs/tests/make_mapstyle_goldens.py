"""The goldens of the mapstyle merge (docs/design/rust_library.md, the design queue, step 6): today's mapstyle output on Monaco, made with
mapstyle (its local checkout) and roadstyle's Python engine (this repository's src/). Run it in the conda environment roadstyle, with no
roadstyle.json, ./palettes or ./profiles of your own, beside the checkouts of mapstyle, duckOSM (its monaco.duckdb) and
geolibre-roadstyle (its build.py), or in the folder $PROJECTS:

    PYTHONPATH=src ROADSTYLE_ENGINE=python python rust/roadstyle-rs/tests/make_mapstyle_goldens.py looks styles

- looks: rust/roadstyle-look/tests/data/mapstyle_looks.json.gz (tests/basemap.rs of roadstyle-look): the 64 looks of geolibre-roadstyle's
  look_of (each mode x theme x path style), each part once (build.looks()). mapstyle makes a mode's palette from a set, so the bytes of
  this file change with each run; the test compares the keys in sorted order.
- styles: mapstyle.export.export_inline of 6 choices into tests/data/mapstyle/ (not in git: about 2.8 MB each, gzipped), and
  tests/data/mapstyle_digests.json (in git): for each style, the sha256 of its canonical JSON (json.dumps with sort_keys and the
  separators "," and ":"), its number of layers and the size of that text. The canonical text is the same with each hash seed."""
import gzip
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECTS = Path(os.environ.get("PROJECTS") or HERE.parents[3].parent)
DB = PROJECTS / "duckOSM" / "monaco.duckdb"
CHOICES = [(m, "osm", "google") for m in ("all", "driving", "walking", "cycling")] + [("all", "grey", "google"), ("walking", "google", "komoot")]


def gz(path, obj):
    path.write_bytes(gzip.compress(json.dumps(obj, separators=(",", ":")).encode(), 9, mtime=0))


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def write_looks():
    spec = importlib.util.spec_from_file_location("glbuild", PROJECTS / "geolibre-roadstyle" / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    gz(HERE.parents[1] / "roadstyle-look" / "tests" / "data" / "mapstyle_looks.json.gz", build.looks(DB))


def write_styles():
    from mapstyle.export import export_inline
    out = HERE / "data" / "mapstyle"
    out.mkdir(exist_ok=True)
    digests = {}
    for mode, theme, paths in CHOICES:
        name = f"style_{mode}_{theme}_{paths}"
        style = export_inline(DB, mode=mode, theme=theme, paths=paths)
        gz(out / f"{name}.json.gz", style)
        text = canonical(style)
        digests[name] = {"sha256": hashlib.sha256(text).hexdigest(), "layers": len(style["layers"]), "bytes": len(text)}
        print(name, digests[name])
    (HERE / "data" / "mapstyle_digests.json").write_text(json.dumps(digests, indent=1) + "\n")


if __name__ == "__main__":
    for part in sys.argv[1:]:
        {"looks": write_looks, "styles": write_styles}[part]()
