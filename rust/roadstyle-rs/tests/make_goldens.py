"""The one generator of the Rust goldens (docs/design/rust_library.md, P0): roadstyle's own output (Python) that the Rust tests compare
with. Run it in the conda environment roadstyle (roadstyle from this repository's src/, mapstyle not needed), with no roadstyle.json,
./palettes or ./profiles of your own, one part at a time:

    python rust/roadstyle-rs/tests/make_goldens.py cmaps monaco sodermalm tartu

- tests/data/monaco_part/roads.parquet (the roads of Monaco in BOX, around Monte Carlo) is a fixed input in git: this script made it
  until 2026-10-24, when the colour cases became the Rust engine's own goldens (tests/colors.rs).
- cmaps: src/roadstyle/data/cmaps.json, the colour ramps of both engines (colors.py and roadstyle-look read it), from branca and matplotlib (branca's schemes and colour names, each
  matplotlib colormap at 9 stops).
- level_area: tests/data/level_area/ (tests/level_area.rs): a level area of Monaco in a box, and roadstyle's answers of the check before
  a rule is added.
- monaco, sodermalm, tartu: tests/data/<area>/golden_*.gz (tests/areas.rs): the look's options and the levels (compute_levels' tags
  rule; the solve with duckOSM's level-area defaults, not for Tartu: Python needs 4.8 GB and 85 s for Monaco). The areas' style and tiles
  are the Rust engine's own goldens since 2026-10-24 (tests/areas.rs, ROADSTYLE_BLESS=1). sodermalm also writes its input, tests/data/sodermalm/roads.parquet, from
  notebooks/data/sodermalm_edges.gpkg with the solved levels. tartu reads tests/data/tartu/ (tests/get_goldens.sh) and writes to
  tests/data/tartu/, whose goldens go to the pre-release rust-test-data (their SHA-256 are in tests/areas.rs)."""
import gzip
import json
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

def write_area(area):
    if area == "sodermalm":
        sodermalm_input()
    g = read_roads(DATA / area / "roads.parquet")
    o = area_options(area)
    kw = {**o["args"], "arrows": True, "labels": True, "view_3d": False}     # the engine: names and arrows always, no decks
    out = {}
    out["options"] = {**o, "args": kw}
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
    parts = sys.argv[1:] or ["cmaps", "monaco", "sodermalm"]
    warnings.simplefilter("ignore", DeprecationWarning)
    for p in parts:
        {"cmaps": write_cmaps, "level_area": write_level_area}.get(p, lambda p=p: write_area(p))()

if __name__ == "__main__":
    main()
