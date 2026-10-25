"""The goldens of the mapstyle merge (docs/design/rust_library.md, the design queue, step 6): today's mapstyle output on Monaco, made with
mapstyle (its local checkout) and roadstyle's Python engine (this repository's src/). Run it in the conda environment roadstyle, with no
roadstyle.json, ./palettes or ./profiles of your own, beside the checkouts of mapstyle, duckOSM (its monaco.duckdb) and
geolibre-roadstyle (its build.py), or in the folder $PROJECTS:

    PYTHONPATH=src ROADSTYLE_ENGINE=python python rust/roadstyle-rs/tests/make_mapstyle_goldens.py looks styles

- looks: rust/roadstyle-look/tests/data/mapstyle_looks.json.gz (tests/basemap.rs of roadstyle-look): the 64 looks of geolibre-roadstyle's
  look_of (each mode x theme x path style), each part once (build.looks()). mapstyle makes a mode's palette from a set, so the bytes of
  this file change with each run; the test compares the keys in sorted order.
- styles: mapstyle.export.export_inline of 8 choices (2 of them the map of one mode, only=True), with access_col="access", into
  tests/data/mapstyle/ (not in git: about 2.8 MB each, gzipped), and
  tests/data/mapstyle_digests.json (in git): for each style, the sha256 of its canonical JSON (json.dumps with sort_keys and the
  separators "," and ":"), its number of layers and the size of that text (the record), and the same three of its normalised form
  (`normalised`: what tests/test_duckosm.py compares with the Rust engine's style). The canonical text is the same with each hash seed.
- renormalise: the normalised digests again from the stored styles, after a rule of `normalised` changed (the record stays)."""
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
    - the 3D decks as their chains, each with the set of its features' edges, slab flag, base, height and heads (`_deck_chains`): GEOS's
      offset curve cuts a curved slice into 0 to n parts, Rust draws one mitre strip for each side (tests/test_engine_parity.py's
      test_export_inline_decks_on_curves); the union area of each chain's decks and slabs is compared apart (`deck_areas`, DECK_AREA);
    - a polygon by its rings, not by the order of its parts, the start point or the orientation of a ring (the background's land:
      mapstyle cuts the sea out with GEOS, the Rust reader with i_overlay, which writes the same points in another order);
    - a slot's road (`__rs_edge`, `__rs_edge2`) as the road or its undirected twin, the lower row of the two (the same line reversed, the
      same class, both not directed): a tie between undirected twins: GEOS's tree order in Python, float rounding in Rust; same geometry;
    - an attached point's road (`edge_id`, `__rs_edge` of a crossing or a traffic signal) as the lowest row of the roads at its smallest
      distance, when its road is one of them: a tie of edge_attach's "the nearest road" (no road within 3e-5 deg): GEOS's tree order in
      Python (STRtree.query_nearest), the first row in Rust; the same distance."""
    twin = _undirected_twins(style)
    attached = _attached_ties(style)
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
    for name, rows in attached.items():
        for k, (row, edge_id) in rows.items():
            props = out["sources"][name]["data"]["features"][k]["properties"]
            props["__rs_edge"], props["edge_id"] = row, edge_id
    if "decks" in out["sources"]:
        out["sources"]["decks"]["data"] = {"chains": _deck_chains(style)}
    for src in out["sources"].values():
        for f in (src.get("data") or {}).get("features", []) if isinstance(src.get("data"), dict) else []:
            g = f.get("geometry") or {}
            if g.get("type") in ("Polygon", "MultiPolygon"):
                f["geometry"] = {"type": "MultiPolygon", "rings": _rings(g)}
    return out


DECK_KEYS = ("__rs_edges", "__rs_casing_slab", "__rs_base", "__rs_height", "__rs_hs", "__rs_he")
# the union area of a chain's decks and of its slabs, as a part of mapstyle's: tests/test_engine_parity.py's _DECK_AREA and _SLAB_AREA
DECK_AREA = {False: 0.005, True: 0.05}


def _decks(style):
    return ((style["sources"].get("decks") or {}).get("data") or {}).get("features") or []


def _deck_chains(style):
    """{chain: the sorted set of its features' DECK_KEYS values (as JSON text)}."""
    out = {}
    for f in _decks(style):
        p = f["properties"]
        out.setdefault(str(p["__rs_chain"]), set()).add(json.dumps([p.get(k) for k in DECK_KEYS]))
    return {c: sorted(v) for c, v in sorted(out.items())}


def deck_areas(style):
    """{(chain, slab): the union area of the chain's decks (slab False) or casing slabs (True)}."""
    from shapely import make_valid
    from shapely.geometry import shape
    from shapely.ops import unary_union
    parts = {}
    for f in _decks(style):
        p = f["properties"]
        parts.setdefault((str(p["__rs_chain"]), bool(p.get("__rs_casing_slab"))), []).append(make_valid(shape(f["geometry"])))
    return {k: unary_union(v).area for k, v in parts.items()}


def stored(name):
    """The stored mapstyle style `name` (tests/data/mapstyle/, not in git)."""
    return json.loads(gzip.decompress((HERE / "data" / "mapstyle" / f"{name}.json.gz").read_bytes()))


def _attached_ties(style):
    """{source: {feature index: (road row, edge_id)}} for each point of a base-map layer that names a road (edge_attach) when that road is
    one of two or more roads at the point's smallest distance: the lowest row of them and its edge_id (as text)."""
    import shapely
    roads = ((style["sources"].get("roads") or {}).get("data") or {}).get("features") or []
    rows = [f["properties"].get("__rs_edge") for f in roads]
    lines = shapely.from_geojson([json.dumps(f["geometry"]) for f in roads]) if roads else []
    tree = shapely.STRtree(lines) if roads else None
    out = {}
    for name, src in style["sources"].items():
        if not name.startswith("ov") or tree is None:
            continue
        for k, f in enumerate((src.get("data") or {}).get("features") or []):
            p, g = f.get("properties") or {}, f.get("geometry") or {}
            if g.get("type") != "Point" or "__rs_edge" not in p:
                continue
            idx, d = tree.query_nearest(shapely.Point(g["coordinates"]), all_matches=True, return_distance=True)
            tied = sorted(rows[i] for i in idx)
            if len(tied) > 1 and p["__rs_edge"] in tied:
                low = tied[0]
                out.setdefault(name, {})[k] = (low, str(roads[rows.index(low)]["properties"]["edge_id"]))
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


def _hex(v):
    """The channels of a hex colour ("#rrggbb" or "#rgb"); None for any other value."""
    if not isinstance(v, str) or not v.startswith("#") or len(v) not in (4, 7):
        return None
    h = v[1:] if len(v) == 7 else "".join(c * 2 for c in v[1:])
    try:
        return bytes.fromhex(h)
    except ValueError:
        return None


def differences(a, b, path="", out=None, limit=10):
    """The places where two normalised styles differ (at most `limit`), two hex colours within 1 in each channel taken as the same: the Rust
    look rounds a mixed colour half up (roadstyle_look::color::mix, review D4, 2026-10-24), mapstyle's _mix half to even; the picture is the
    same."""
    out = [] if out is None else out
    if len(out) >= limit or a == b:
        return out
    x, y = _hex(a), _hex(b)
    if x is not None and y is not None and all(abs(p - q) <= 1 for p, q in zip(x, y, strict=True)):
        return out
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        for k in a:
            differences(a[k], b[k], f"{path}.{k}", out, limit)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (u, v) in enumerate(zip(a, b, strict=True)):
            differences(u, v, f"{path}[{i}]", out, limit)
    else:
        out.append(f"{path}: {str(a)[:120]} != {str(b)[:120]}")
    return out


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
        # access_col: the restricted roads' colour baked into the fills by Python's render (2026-10-24, for the dashboard's port of
        # mapstyle's page scripts; mapstyle's layers.js painted the same colours on the page, so the picture is the same)
        style = export_inline(DB, mode=mode, theme=theme, paths=paths, access_col="access", **({"only": True} if only else {}))
        gz(out / f"{name}.json.gz", style)
        digests[name] = {**digest(style), "normalised": digest(normalised(style))}
        print(name, digests[name])
    (HERE / "data" / "mapstyle_digests.json").write_text(json.dumps(digests, indent=1) + "\n")


def renormalise():
    """The normalised digests again from the stored styles (after a rule of `normalised` changed), each style's record digest unchanged."""
    path = HERE / "data" / "mapstyle_digests.json"
    digests = json.loads(path.read_text())
    for name, d in digests.items():
        style = stored(name)
        assert {k: v for k, v in digest(style).items()} == {k: d[k] for k in ("sha256", "layers", "bytes")}, f"{name}: not the stored golden"
        d["normalised"] = digest(normalised(style))
        print(name, d["normalised"])
    path.write_text(json.dumps(digests, indent=1) + "\n")


if __name__ == "__main__":
    for part in sys.argv[1:]:
        {"looks": write_looks, "styles": write_styles, "renormalise": renormalise}[part]()
