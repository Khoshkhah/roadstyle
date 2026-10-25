"""The inputs of the Rust tests that Python makes (docs/design/rust_library.md, P0). Since 2026-10-24 the Rust tests compare with
goldens that the Rust engine makes (ROADSTYLE_BLESS=1 cargo test; the Rust API is the design), so this script makes no reference
output any more. Run it in the conda environment roadstyle (roadstyle from this repository's src/, mapstyle not needed), with no
roadstyle.json, ./palettes or ./profiles of your own, one part at a time:

    python rust/roadstyle-rs/tests/make_goldens.py cmaps monaco sodermalm tartu

- cmaps: src/roadstyle/data/cmaps.json, the colour ramps of both engines (colors.py and roadstyle-look read it), from branca and
  matplotlib (branca's schemes and colour names, each matplotlib colormap at 9 stops).
- monaco, sodermalm, tartu: tests/data/<area>/golden_options.json.gz, the look's options of the area (tests/areas.rs, level_options.rs).
  sodermalm also writes its input, tests/data/sodermalm/roads.parquet, from notebooks/data/sodermalm_edges.gpkg with duckOSM's solved
  levels (roadstyle's level_input and solve_levels with the level area's defaults).
- Fixed inputs in git that this script made before: tests/data/monaco_part/roads.parquet (the roads of Monaco in BOX, around Monte
  Carlo) and tests/data/level_area/edges.parquet (a level area's input, the roads of Monaco in BOX). Tartu's inputs are on the
  pre-release rust-test-data (tests/get_goldens.sh)."""
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
    o = area_options(area)
    kw = {**o["args"], "arrows": True, "labels": True, "view_3d": False}     # the engine: names and arrows always, no decks
    out = {}
    out["options"] = {**o, "args": kw}
    for k, v in out.items():
        p = DATA / area / f"golden_{k}.json.gz"
        p.write_bytes(gzip.compress(json.dumps(v, separators=(",", ":")).encode(), 9, mtime=0))
        print(f"{area}: {p.name} {p.stat().st_size // 1000} KB")

def main():
    parts = sys.argv[1:] or ["cmaps", "monaco", "sodermalm"]
    warnings.simplefilter("ignore", DeprecationWarning)
    for p in parts:
        {"cmaps": write_cmaps}.get(p, lambda p=p: write_area(p))()

if __name__ == "__main__":
    main()
