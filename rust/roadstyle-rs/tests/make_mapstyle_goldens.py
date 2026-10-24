"""The goldens of the mapstyle merge (docs/design/rust_library.md, the design queue, step 6): today's mapstyle output on Monaco, made with
mapstyle (its local checkout) and roadstyle's Python engine (this repository's src/). Run it in the conda environment roadstyle, with no
roadstyle.json, ./palettes or ./profiles of your own, beside the checkouts of mapstyle, duckOSM (its monaco.duckdb) and
geolibre-roadstyle (its build.py), or in the folder $PROJECTS:

    PYTHONPATH=src ROADSTYLE_ENGINE=python python rust/roadstyle-rs/tests/make_mapstyle_goldens.py looks styles

- looks: rust/roadstyle-look/tests/data/mapstyle_looks.json.gz (tests/basemap.rs of roadstyle-look): the 64 looks of geolibre-roadstyle's
  look_of (each mode x theme x path style), each part once (build.looks()). mapstyle makes a mode's palette from a set, so the bytes of
  this file change with each run; the test compares the keys in sorted order.
- styles: mapstyle.export.export_inline of 8 choices (2 of them the map of one mode, only=True) into tests/data/mapstyle/ (not in git: about 2.8 MB each, gzipped), and
  tests/data/mapstyle_digests.json (in git): for each style, the sha256 of its canonical JSON (json.dumps with sort_keys and the
  separators "," and ":"), its number of layers and the size of that text (the record), and the same three of its normalised form
  (`normalised`: what tests/test_duckosm.py compares with the Rust engine's style). The canonical text is the same with each hash seed."""
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
# (mode, theme, path style, only: the map of the mode alone)
CHOICES = ([(m, "osm", "google", False) for m in ("all", "driving", "walking", "cycling")] + [("all", "grey", "google", False),
           ("walking", "google", "komoot", False)] + [(m, "osm", "google", True) for m in ("driving", "walking")])


def name_of(mode, theme, paths, only):
    return f"style_{mode}_{theme}_{paths}" + ("_only" if only else "")


def gz(path, obj):
    path.write_bytes(gzip.compress(json.dumps(obj, separators=(",", ":")).encode(), 9, mtime=0))


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _pixels(url):
    """A PNG data URL as its size and its RGBA pixels (sha256)."""
    import base64
    import io

    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")
    return {"png": list(im.size), "rgba": hashlib.sha256(im.tobytes()).hexdigest()}


def normalised(style):
    """The style with the differences that were decided, each by its rule, so that the Rust engine's style of the same map has the same
    digest:
    - ids as text: `osm_id` and `edge_id` of every feature (mapstyle reads them as text; the Rust reader keeps them BIGINT: N1, R13);
    - no `source` and `target` on a road (the Rust reader keeps them: R13);
    - every coordinate to 9 places (the Rust engine computes a centroid, mapstyle uses shapely: the last digit can differ);
    - each PNG image as its pixels (the Rust engine's PNG encoder writes other bytes for the same image);
    - the 3D decks without their geometry (Python makes the polygons with GEOS, Rust with its own offsets: tests/test_engine_parity.py's
      test_export_inline_decks compares them by shape);
    - a polygon by its rings, not by the order of its parts, the start point or the orientation of a ring (the background's land:
      mapstyle cuts the sea out with GEOS, the Rust reader with i_overlay, which writes the same points in another order);
    - a slot's road (`__rs_edge`, `__rs_edge2`) as the road or its undirected twin, the lower row of the two (the same line reversed, the
      same class, both not directed): a tie between undirected twins: GEOS's tree order in Python, float rounding in Rust; same geometry."""
    twin = _undirected_twins(style)
    def walk(o, key=None):
        if isinstance(o, dict):
            drop = ("source", "target") if key == "properties" else ()
            return {k: walk(v, k) for k, v in o.items() if k not in drop}
        if isinstance(o, list):
            return [walk(v, key) for v in o]
        if key in ("osm_id", "edge_id") and isinstance(o, int) and not isinstance(o, bool):
            return str(o)
        if key in ("__rs_edge", "__rs_edge2") and isinstance(o, int) and in_slots[0]:
            return min(o, twin.get(o, o))
        if key == "coordinates" and isinstance(o, float):
            return round(o, 9)
        if isinstance(o, str) and o.startswith("data:image/png;base64,"):
            return _pixels(o)
        return o
    in_slots = [False]
    out = {k: v for k, v in style.items() if k != "sources"}
    out = walk(out)
    out["sources"] = {}
    for name, src in style["sources"].items():
        in_slots[0] = name == "slots"
        out["sources"][name] = walk(src)
    in_slots[0] = False
    out = {k: out[k] for k in style}
    for f in out["sources"].get("decks", {}).get("data", {}).get("features", []):
        f.pop("geometry", None)
    for src in out["sources"].values():
        for f in (src.get("data") or {}).get("features", []) if isinstance(src.get("data"), dict) else []:
            g = f.get("geometry") or {}
            if g.get("type") in ("Polygon", "MultiPolygon"):
                f["geometry"] = {"type": "MultiPolygon", "rings": _rings(g)}
    return out


def _undirected_twins(style):
    """{road row: its twin's row} for each pair of roads on the same line the other way round, of the same class, both not directed."""
    feats = ((style["sources"].get("roads") or {}).get("data") or {}).get("features") or []
    by_line, out = {}, {}
    for f in feats:
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        if p.get("is_directed") or g.get("type") != "LineString" or "__rs_edge" not in p:
            continue
        line = tuple(map(tuple, g["coordinates"]))
        j = by_line.get((line[::-1], p.get("highway")))
        if j is not None:
            out[p["__rs_edge"]], out[j] = j, p["__rs_edge"]
        by_line[(line, p.get("highway"))] = p["__rs_edge"]
    return out


def _rings(g):
    """A polygon's parts as sorted lists of rings, each ring open, from its smallest point, in the direction of its smaller second point."""
    def ring(r):
        r = [tuple(p) for p in r]
        if len(r) > 1 and r[0] == r[-1]:
            r = r[:-1]
        forms = []
        for q in (r, r[::-1]):
            k = q.index(min(q))
            forms.append(q[k:] + q[:k])
        return [list(p) for p in min(forms)]
    parts = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    return sorted(sorted(ring(r) for r in part) for part in parts)


def digest(style):
    text = canonical(style)
    return {"sha256": hashlib.sha256(text).hexdigest(), "layers": len(style["layers"]), "bytes": len(text)}


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
    for mode, theme, paths, only in CHOICES:
        name = name_of(mode, theme, paths, only)
        style = export_inline(DB, mode=mode, theme=theme, paths=paths, **({"only": True} if only else {}))
        gz(out / f"{name}.json.gz", style)
        digests[name] = {**digest(style), "normalised": digest(normalised(style))}
        print(name, digests[name])
    (HERE / "data" / "mapstyle_digests.json").write_text(json.dumps(digests, indent=1) + "\n")


if __name__ == "__main__":
    for part in sys.argv[1:]:
        {"looks": write_looks, "styles": write_styles}[part]()
