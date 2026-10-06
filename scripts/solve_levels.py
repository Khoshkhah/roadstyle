"""Solve the drawing levels (docs/design/level_input.md): OUT_DIR/roads.parquet + pairs.csv + edits.csv -> OUT_DIR/levels.csv.

    python scripts/solve_levels.py OUT_DIR

levels.csv has one row per edge: edge (its id), casing_start, casing_level, casing_end, fill_level; draw them with
rs.render_edges(edges, casing_start_col=..., casing_level_col=..., casing_end_col=..., fill_level_col=...).
"""
import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd

import roadstyle as rs


def edge_levels(solved):
    """One row per edge from one row per road: an edge running the other way has its two heads swapped."""
    rows = []
    for r in solved.itertuples():
        for e in r.edges:
            rows.append((e, r.casing_start, r.casing_level, r.casing_end, r.fill_level))
        for e in r.reversed:
            rows.append((e, r.casing_end, r.casing_level, r.casing_start, r.fill_level))
    return pd.DataFrame(rows, columns=["edge", "casing_start", "casing_level", "casing_end", "fill_level"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--head-m", type=float, default=5.0, help="metres of casing head at each end of a road (default 5)")
    a = ap.parse_args(argv)
    roads = gpd.read_parquet(a.out_dir / "roads.parquet")
    edits = a.out_dir / "edits.csv"
    solved = rs.solve_levels(roads, a.out_dir / "pairs.csv", edits=edits if edits.exists() else None, head_m=a.head_m)
    edge_levels(solved).to_csv(a.out_dir / "levels.csv", index=False)
    info = solved.attrs["levels_info"]
    print(f"{len(roads)} roads -> {a.out_dir / 'levels.csv'}: {len(solved.attrs['levels_given_up'])} stack pair(s) given up, "
          f"{info.get('order_violations', 0)} order wish(es) not kept, {info.get('seconds')} s")


if __name__ == "__main__":
    main()
