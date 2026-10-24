"""The one generator of the Rust goldens (docs/design/rust_library.md, P0): roadstyle's own output (Python) that the Rust tests compare
with. Run it in the conda environment roadstyle (roadstyle from this repository's src/, mapstyle not needed), with no roadstyle.json,
./palettes or ./profiles of your own, one part at a time:

    python rust/roadstyle-rs/tests/make_goldens.py cmaps colors looks monaco sodermalm tartu

- cmaps: src/roadstyle/data/cmaps.json, the colour ramps of both engines (colors.py and roadstyle-look read it), from branca and matplotlib (branca's schemes and colour names, each
  matplotlib colormap at 9 stops).
- colors: tests/data/monaco_part/ (tests/colors.rs): the roads of Monaco in a box around Monte Carlo, and for each case of data colour
  <case>.json.gz = {"args", "style": export_inline's style, "color_options": the page's colour options (render_web's __COLOR_OPTIONS__)}.
- looks: tests/data/looks.json.gz (tests/look.rs): the look of render_edges' palette, profile and settings, for each built-in profile x
  palette and settings sources in the older and the newer layout.
- level_area: tests/data/level_area/ (tests/level_area.rs): a level area of Monaco in a box, and roadstyle's answers of the check before
  a rule is added.
- monaco, sodermalm, tartu: tests/data/<area>/golden_*.gz (tests/areas.rs): the roads-only style (export_inline), the tiles of
  export_style around the roads' centre, and the levels (compute_levels' tags rule; the solve with duckOSM's level-area defaults, not for
  Tartu: Python needs 4.8 GB and 85 s for Monaco). sodermalm also writes its input, tests/data/sodermalm/roads.parquet, from
  notebooks/data/sodermalm_edges.gpkg with the solved levels. tartu reads tests/data/tartu/ (tests/get_goldens.sh) and writes to
  tests/data/tartu/, whose goldens go to the pre-release rust-test-data (their SHA-256 are in tests/areas.rs)."""
import base64
import gzip
import json
import re
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely

import roadstyle as rs

DATA = Path(__file__).resolve().parent / "data"
REPO = Path(__file__).resolve().parents[3]
BOX = (7.4205, 43.7360, 7.4265, 43.7410)        # lon / lat: Monte Carlo, about 480 m x 550 m

def color_table(roads):
    """Every third road: one of three colours, by its edge_id (the keys as text, as a JSON object has them)."""
    cols = ["#e41a1c", "#377eb8", "#4daf4a"]
    return {str(e): cols[i % 3] for i, e in enumerate(roads["edge_id"]) if i % 3 == 0}

CASES = {
    "plain": lambda r: {},
    "numeric": lambda r: {"color_by": "lanes", "cmap": "YlOrRd", "vmin": 1, "vmax": 4},
    "numeric_width": lambda r: {"color_by": "lanes", "cmap": "viridis", "width_by": [1.0, 6.0]},
    "categorical": lambda r: {"color_by": "access", "colors": {"private": "#d62728", "destination": "#ff7f0e", "no": "#7f7f7f"}},
    "color_table": lambda r: {"color_table": color_table(r)},
    "color_options": lambda r: {"color_options": {"class": {}, "lanes": {"color_by": "lanes", "cmap": "Blues", "vmin": 1, "vmax": 3},
                                                  "access": {"color_by": "access", "colors": {"private": "#d62728"}, "missing": "self"}},
                                "color_active": "lanes"},
    "no_legend": lambda r: {"color_by": "lanes", "cmap": "magma", "legend": False},
}

def write_cmaps():
    import os

    import branca
    import branca.colormap as bcm
    import matplotlib
    from matplotlib import colors as mcolors

    root = os.path.dirname(bcm.__file__)
    schemes = json.loads(Path(root, "_schemes.json").read_text())
    css = json.loads(Path(root, "_cnames.json").read_text())
    mpl = {n: [mcolors.to_hex(matplotlib.colormaps[n](i / 8.0)) for i in range(9)] for n in sorted(matplotlib.colormaps)}
    out = {"versions": {"branca": branca.__version__, "matplotlib": matplotlib.__version__}, "branca": schemes, "css": css, "matplotlib": mpl}
    Path(__file__).resolve().parents[3].joinpath("src", "roadstyle", "data", "cmaps.json").write_text(json.dumps(out, separators=(",", ":")))

def write_colors():
    look = json.loads((DATA / "look.json").read_text())
    t = pq.read_table(DATA / "monaco" / "roads.parquet")     # plain Parquet, the geometry as WKB (as the worker's SQL writes it)
    b = shapely.bounds(shapely.from_wkb(t.column("geometry").to_pylist()))
    inside = (b[:, 0] >= BOX[0]) & (b[:, 2] <= BOX[2]) & (b[:, 1] >= BOX[1]) & (b[:, 3] <= BOX[3])
    out = DATA / "monaco_part"
    pq.write_table(t.filter(pa.array(inside)), out / "roads.parquet", compression="snappy")
    df = pq.read_table(out / "roads.parquet").to_pandas(integer_object_nulls=True)     # what the Rust test reads (integers stay integers)
    part = gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")
    kw = {**look["args"], "arrows": True, "labels": True}      # the engine always makes the names and arrows
    for name, opts in CASES.items():
        o = opts(part)
        style = rs.export_inline(part, palette=look["palette"], settings=look["settings"], **kw, **o)
        page = rs.render_edges(part, backend="web", palette=look["palette"], settings=look["settings"], **kw, **o)
        html = page if isinstance(page, str) else getattr(page, "html", None) or page.data
        meta = json.loads(re.search(r"\n\s*color_options: (.*?),\n", html).group(1))     # the page's colour options (render_web: __COLOR_OPTIONS__)
        (out / f"{name}.json.gz").write_bytes(gzip.compress(json.dumps({"args": o, "style": style, "color_options": meta},
                                                                       separators=(",", ":")).encode(), 9, mtime=0))
        feats = style["sources"]["roads"]["data"]["features"]
        print(f"{name:14s} {len(feats)} roads, {len(style['layers'])} layers, color options {[m['name'] for m in meta]}, "
              f"{(out / f'{name}.json.gz').stat().st_size // 1000} KB")

def _json(o):
    """numpy values, sets and tuples that json cannot write (as geolibre-roadstyle's build.py writes the look)."""
    if hasattr(o, "item"):
        return o.item()
    if isinstance(o, (set, frozenset, tuple)):
        return sorted(o, key=str) if isinstance(o, (set, frozenset)) else list(o)
    raise TypeError(f"{type(o)} is not JSON")

def py_look(palette="amber", profile=None, settings=None, args=None):
    """The roadstyle half of geolibre-roadstyle's look_of (build.py): the look render_edges(palette=, profile=, settings=) renders with,
    with no base-map part (mapstyle's "features")."""
    import base64
    import dataclasses
    import inspect
    from importlib.resources import files

    from roadstyle import _settings
    from roadstyle import render_web as rw
    from roadstyle.palettes import FALLBACK, PALETTES
    from roadstyle.style import _apply
    from roadstyle.stylers import _dash_str

    active = _settings.theme()["active"]         # render_edges: a profile / palette by name is a settings source after settings=
    pick = {k: v for k, v in (("profile", profile), ("palette", palette)) if v is not None and v != active[k]
            and (k == "profile" or v in _settings.style_names("palettes"))}
    sources = ([settings] if settings is not None else []) + ([pick] if pick else [])
    prev = list(_settings._EXTRA)
    rs.use_settings(*prev, *sources)
    try:
        table = PALETTES[palette]

        def res(st):
            out = []
            for link in (False, True):
                q = _apply(st, link, False, False, rw.CONFIG)
                out.append({"fill": q.fill, "width": q.width, "casing": q.casing, "casing_width": q.casing_width, "dash": _dash_str(q.dash),
                            "opacity": q.opacity, "casing_opacity": q.casing_opacity})
            return out
        styles = {"classes": {c: res(st) for c, st in table.items()}, "fallback": res(table.get(FALLBACK) or next(iter(table.values())))}
        png = files("roadstyle").joinpath("data/sprite.png").read_bytes()
        look = {"palette": palette, "settings": settings, "args": args or {}, "theme": _settings.theme(), "config": dataclasses.asdict(rw.CONFIG),
                "styles": styles, "head_m": inspect.signature(rw.render).parameters["head_m"].default,
                "slots": {"z_order": dict(rw.ROAD_Z), "width_z20": {c: rw.class_width_px(c, 20) for c in rw._CLASSES},
                          "width_z20_fallback": rw.class_width_px(None, 20)},
                "roads_model": _settings.roads(),
                "oneway_image": {"url": "data:image/png;base64," + base64.b64encode(png).decode(), "sdf": True,
                                 "pixelRatio": _settings.theme_value("arrows.icon")["pixel_ratio"]},
                "interaction": {"popup": list(rw.DEFAULT_ROAD_POPUP), "hover_delay_ms": inspect.signature(rw.render).parameters["hover_delay_ms"].default}}
    finally:
        rs.use_settings(*prev)
    return json.loads(json.dumps(look, default=_json))

def write_looks():
    import warnings
    cases = [{"palette": pa, "profile": pr} for pr in ("default", "highsat") for pa in ("amber", "carto", "highsat", "mono")]
    cases += [
        # the older layout (as mapstyle writes it): a palette of its own under "palettes", config and selection keys, a roads table
        {"palette": "mine", "settings": {"palettes": {"mine": {"residential": {"fill": "#123456", "width": 2.5, "casing_width": 3.0, "casing": "#654321"},
                                                               "unclassified": {"fill": "#abcdef", "width": 2, "casing_width": 3, "dash": [4, 2]}}},
                                         "config": {"fill_opacity": 0.8, "minor_no_casing": ["footway"], "minzoom": {"service": 14}, "basemap": "osm"},
                                         "selection": {"core": "#ff0000"}, "roads": {"z_order": {"service": 3}}}},
        # the newer layout: a profile and a palette by name, and a style value
        {"settings": {"profile": "highsat", "palette": "carto", "labels": {"color": "#112233"}}, "palette": "carto"},
    ]
    out = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)     # the older layout's warning
        for c in cases:
            out.append({"options": c, "look": py_look(**c)})
    (DATA / "looks.json.gz").write_bytes(gzip.compress(json.dumps(out, separators=(",", ":")).encode(), 9, mtime=0))
    print(f"looks: {len(out)} cases, {(DATA / 'looks.json.gz').stat().st_size // 1000} KB")

def read_roads(path):
    """A plain Parquet file of roads (the geometry as WKB, as the worker's SQL writes it) as GeoPandas gives it to roadstyle; integers
    stay integers."""
    df = pq.read_table(path).to_pandas(integer_object_nulls=True)
    return gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")

LEVELS = ["casing_start", "casing_level", "casing_end", "fill_level"]

def solved(g):
    """duckOSM's levels: roadstyle's level_input and solve_levels with the level area's defaults (tools/compare_levels.py of duckosm-rust)."""
    from roadstyle import level_area
    roads, pairs = rs.level_input(g, id_col="edge_id")
    ref = level_area.edge_levels(rs.solve_levels(roads, pairs), level_area.defaults(roads, pairs)).rename(columns={"edge": "edge_id"})
    return ref

def sodermalm_input():
    """tests/data/sodermalm/roads.parquet: the Södermalm sample (driving edges) with duckOSM's solved levels, in the engine's columns."""
    g = gpd.read_file(REPO / "notebooks" / "data" / "sodermalm_edges.gpkg")
    lv = solved(g)
    lv["edge_id"] = lv["edge_id"].astype(str)
    g["edge_id"] = g["edge_id"].astype(str)          # as text, as in the Monaco fixture (the ids pass 2**53)
    g = g.merge(lv, on="edge_id", how="left")
    assert g["fill_level"].notna().all(), "an edge without levels"
    t = pa.Table.from_pandas(g.drop(columns="geometry"), preserve_index=False)
    t = t.append_column("geometry", pa.array(shapely.to_wkb(g.geometry.values), pa.binary()))
    (DATA / "sodermalm").mkdir(exist_ok=True)
    pq.write_table(t, DATA / "sodermalm" / "roads.parquet", compression="snappy")

def area_options(area):
    """The look's options for an area: the fixture's look (mapstyle's palette and settings) for Monaco and Tartu, amber for Södermalm."""
    look = json.loads((DATA / "look.json").read_text())
    if area == "sodermalm":
        args = {"name": "sodermalm", "tooltip": ["edge_id", "highway", "name"], "basemap": "blank",
                **{f"{c}_col": c for c in ["casing_start", "casing_level", "casing_end", "fill_level", "head_start_m", "head_end_m", "cap_start", "cap_end"]}}
        return {"palette": "amber", "settings": None, "args": args}
    return {"palette": look["palette"], "settings": look["settings"], "args": look["args"]}

def tile_names(g, zooms=(12, 14, 15)):
    """The 3 x 3 tiles around the roads' centre at each zoom."""
    import math
    x0, y0, x1, y1 = g.total_bounds
    lon, lat = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    for z in zooms:
        n = 2 ** z
        x = int((lon + 180) / 360 * n)
        y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
        out += [f"{z}/{x + dx}/{y + dy}" for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
    return out

def write_area(area):
    import tempfile
    if area == "sodermalm":
        sodermalm_input()
    g = read_roads(DATA / area / "roads.parquet")
    o = area_options(area)
    kw = {**o["args"], "arrows": True, "labels": True, "view_3d": False}     # the engine: names and arrows always, no decks
    out = {}
    out["options"] = {**o, "args": kw}
    out["style"] = rs.export_inline(g, palette=o["palette"], settings=o["settings"], **kw)
    with tempfile.TemporaryDirectory() as d:
        tkw = {k: v for k, v in kw.items() if k not in ("basemap", "basemaps")}      # export_style: the app gives the base map
        st = rs.export_style(g, d, base_url="http://localhost/", format="xyz", palette=o["palette"], settings=o["settings"], **tkw)
        out["tiles_style"] = json.loads(Path(st).read_text())
        out["tiles"] = {n: base64.b64encode(p.read_bytes()).decode() for n in tile_names(g)
                        if (p := Path(d) / "tiles" / f"{n}.pbf").is_file()}
    tags = rs.compute_levels(g, method="tags")
    out["levels_tags"] = [[str(e), *map(int, v)] for e, *v in tags[["edge_id", *LEVELS]].itertuples(index=False)]
    if area != "tartu":
        s = solved(g)
        out["levels_solve"] = [[str(r.edge_id), *(int(getattr(r, c)) for c in LEVELS), float(r.head_start_m), float(r.head_end_m), r.cap_start, r.cap_end]
                               for r in s.itertuples(index=False)]
    for k, v in out.items():
        p = DATA / area / f"golden_{k}.json.gz"
        p.write_bytes(gzip.compress(json.dumps(v, separators=(",", ":")).encode(), 9, mtime=0))
        print(f"{area}: {p.name} {p.stat().st_size // 1000} KB")

def write_level_area():
    """tests/data/level_area/ (tests/level_area.rs): a level area of the roads of Monaco in BOX (edges.parquet, make's input; make_area:
    roads.parquet, pairs.csv), and checks.json: rules to add, and what roadstyle's rule_conflicts says of each (its index and why)."""
    import pandas as pd

    from roadstyle.level_area import make_area
    from roadstyle.levels import rule_conflicts
    g = read_roads(DATA / "monaco" / "roads.parquet")
    b = g.geometry.bounds
    g = g[(b.minx >= BOX[0]) & (b.maxx <= BOX[2]) & (b.miny >= BOX[1]) & (b.maxy <= BOX[3])].drop(
        columns=["casing_start", "casing_level", "casing_end", "fill_level"], errors="ignore").reset_index(drop=True)
    out = DATA / "level_area"
    out.mkdir(exist_ok=True)
    t = pa.Table.from_pandas(g.drop(columns="geometry"), preserve_index=False)      # make's input, for Rust's make (tests/level_area.rs)
    pq.write_table(t.append_column("geometry", pa.array(shapely.to_wkb(g.geometry.values), pa.binary())), out / "edges.parquet", compression="snappy")
    roads, pairs = make_area(g, out)
    (out / "edits.csv").unlink(missing_ok=True)
    order, stack = pairs[pairs.relation == "order"].iloc[0], pairs[pairs.relation == "stack"].iloc[0]
    rows = [{**order.to_dict(), "enabled": "true"},                                                      # already there
            {"relation": "order", "a": stack.b, "b": stack.a, "a_end": "", "b_end": "", "enabled": "true"},  # a loop with the stack
            {"relation": "order", "a": roads.road.iat[0], "b": roads.road.iat[-1], "a_end": "", "b_end": "", "enabled": "true"}]
    rows = [{k: ("" if v is None or v != v else str(v)) for k, v in r.items()} for r in rows]
    found = rule_conflicts(roads, pairs, None, rows)
    (out / "checks.json").write_text(json.dumps({"rows": rows, "conflicts": [[rows.index(r), why] for r, why, _ in found]}, indent=1))
    print(f"level_area: {len(roads)} roads, {len(pairs)} pairs, conflicts {[why for _, why, _ in found]}")

def main():
    parts = sys.argv[1:] or ["cmaps", "colors", "looks", "monaco", "sodermalm"]
    warnings.simplefilter("ignore", DeprecationWarning)
    for p in parts:
        {"cmaps": write_cmaps, "colors": write_colors, "looks": write_looks, "level_area": write_level_area}.get(p, lambda: write_area(p))()

if __name__ == "__main__":
    main()
