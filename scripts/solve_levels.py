"""Solve the drawing levels (docs/design/level_input.md): OUT_DIR/roads.parquet + pairs.csv + edits.csv -> OUT_DIR/levels.csv.

    python scripts/solve_levels.py OUT_DIR

levels.csv has one row per edge: edge (its id), casing_start, casing_level, casing_end, fill_level; draw them with
rs.render_edges(edges, casing_start_col=..., casing_level_col=..., casing_end_col=..., fill_level_col=...). The head lengths are the
drawing's (render_edges' head_m, or head_start_m_col / head_end_m_col; the level editor keeps them in heads.csv); the solver only learns from
them which main parts are empty and which parts of an upper road cross the road under it (--head-m each, or OUT_DIR/heads.csv's own).
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


def write(solved, folder):
    """levels.csv, and levels_info.json: what the solver says about it (the editor shows it without solving again)."""
    import json
    edge_levels(solved).to_csv(Path(folder) / "levels.csv", index=False)
    info = {**solved.attrs["levels_info"], "given_up": [list(p) for p in solved.attrs["levels_given_up"]],
            "given_up_parts": [list(p) for p in solved.attrs.get("levels_given_up_parts", [])],
            "near": [list(p) for p in solved.attrs.get("levels_near", [])]}
    (Path(folder) / "levels_info.json").write_text(json.dumps(info, default=str))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--head-m", type=float, default=5.0, help="the heads' length in the drawing, metres (default 5): a road shorter than two has an empty main part")
    ap.add_argument("--max-positions", type=int, help="at most this many drawing positions (a hard bound: wishes, then stack pairs, give way)")
    a = ap.parse_args(argv)
    roads = gpd.read_parquet(a.out_dir / "roads.parquet")
    edits = a.out_dir / "edits.csv"
    heads = a.out_dir / "heads.csv"
    parts = rs.casing_parts(roads, a.head_m, heads if heads.exists() else None)
    solved = rs.solve_levels(roads, a.out_dir / "pairs.csv", edits=edits if edits.exists() else None, max_positions=a.max_positions, parts=parts)
    write(solved, a.out_dir)
    info = solved.attrs["levels_info"]
    print(f"{len(roads)} roads -> {a.out_dir / 'levels.csv'}: {len(solved.attrs['levels_given_up'])} stack pair(s) given up, "
          f"{len(solved.attrs.get('levels_near', []))} near warning(s), "
          f"{info.get('order_violations', 0)} order wish(es) not kept, {info.get('seconds')} s")


if __name__ == "__main__":
    main()
