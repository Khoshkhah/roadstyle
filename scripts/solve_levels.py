"""Solve the drawing levels (docs/design/level_input.md): OUT_DIR/roads.parquet + pairs.csv + edits.csv -> OUT_DIR/levels.csv.

    python scripts/solve_levels.py OUT_DIR

levels.csv has one row per edge: edge (its id), casing_start, casing_level, casing_end, fill_level, and its ends as drawn: head_start_m,
head_end_m, cap_start, cap_end; draw them with rs.render_edges(edges, casing_start_col=..., casing_level_col=..., casing_end_col=...,
fill_level_col=..., head_start_m_col=..., head_end_m_col=..., cap_start_col=..., cap_end_col=...). The ends are 5 m heads, flat caps where
exactly two roads meet (a bend of 15 degrees at most) and round elsewhere (or with --auto-ends rs.auto_ends' at zoom 18), with yours on top (heads.csv / caps.csv, an empty value: the default; the level editor
writes them). The solver only learns from the head lengths which main
parts are empty and which parts of an upper road cross the road under it.
"""
import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd

import roadstyle as rs


def edge_levels(solved, ends_table):
    """One row per edge from one row per road (and its ends as drawn): an edge running the other way has its two heads and caps swapped."""
    e = ends_table.set_index("road")
    rows = []
    for r in solved.itertuples():
        hs, he, cs, ce = e.loc[r.road, ["start_m", "end_m", "cap_start", "cap_end"]]
        for x in r.edges:
            rows.append((x, r.casing_start, r.casing_level, r.casing_end, r.fill_level, hs, he, cs, ce))
        for x in r.reversed:
            rows.append((x, r.casing_end, r.casing_level, r.casing_start, r.fill_level, he, hs, ce, cs))
    return pd.DataFrame(rows, columns=["edge", "casing_start", "casing_level", "casing_end", "fill_level", "head_start_m", "head_end_m", "cap_start", "cap_end"])


def own(folder):
    """Your own head lengths and caps: heads.csv / caps.csv as {road: (start, end)} ("" = the automatic one)."""
    def read(path, cols):
        if not path.exists():
            return {}
        f = pd.read_csv(path, dtype=str, keep_default_na=False)
        if "cap" in f and "start" not in f:                     # an older caps.csv: one value for both ends
            f["start"] = f["end"] = f["cap"]
        if cols[0] not in f:                                    # older still: only the roads, flat
            f[cols[0]] = f[cols[1]] = "flat"
        return {r: (s, e) for r, s, e in zip(f["road"], f[cols[0]], f[cols[1]], strict=True)}
    return read(Path(folder) / "heads.csv", ("start_m", "end_m")), read(Path(folder) / "caps.csv", ("start", "end"))


def ends(auto, heads, caps):
    """Each road end's head length and cap as drawn: ``auto`` (rs.auto_ends) with ``heads`` / ``caps`` ({road: (start, end)}) on top."""
    t = auto.set_index("road").copy()
    for r, (s, e) in heads.items():
        if r in t.index:
            t.loc[r, "start_m"], t.loc[r, "end_m"] = (float(s) if s else t.loc[r, "start_m"]), (float(e) if e else t.loc[r, "end_m"])
    for r, (s, e) in caps.items():
        if r in t.index:
            t.loc[r, "cap_start"], t.loc[r, "cap_end"] = (s or t.loc[r, "cap_start"]), (e or t.loc[r, "cap_end"])
    return t.reset_index()


def defaults(roads, pairs, head_m=5.0, max_bend=15.0):
    """Every road end as drawn unless you set it: ``head_m`` long heads; a flat cap where exactly two road ends meet (one road going on into
    the next) with a bend of at most ``max_bend`` degrees, round elsewhere (a junction of three or more, a dead end, a sharper bend, where
    two flat ends would leave the outer corner open). Kaveh 2026-10-06; the automatic heads, made for one zoom, were too short at the
    others. ``pairs``: level_input's (its meet rows say which ends meet)."""
    import math
    from collections import defaultdict

    from roadstyle.levels import _metres, _read_pairs
    geo = dict(zip(roads["road"], _metres(roads.geometry), strict=True))
    at = defaultdict(set)                                       # a road end -> the road ends it meets
    for row in _read_pairs(pairs):
        if row["relation"] == "meet":
            at[(row["a"], row["a_end"])].add((row["b"], row["b_end"]))
            at[(row["b"], row["b_end"])].add((row["a"], row["a_end"]))
    def heading(r, end):                                        # leaving the node along the road
        c = list(geo[r].coords) if end == "start" else list(geo[r].coords)[::-1]
        return math.atan2(c[1][1] - c[0][1], c[1][0] - c[0][0])
    def cap(r, end):
        J = at.get((r, end), set())
        if len(J) != 1:
            return "round"
        (o, oe), = J
        if at.get((o, oe), set()) != {(r, end)}:               # the other end meets more roads: a junction
            return "round"
        bend = 180 - abs((math.degrees(heading(r, end) - heading(o, oe)) + 180) % 360 - 180)
        return "flat" if bend <= max_bend else "round"
    ids = list(roads["road"])
    return pd.DataFrame({"road": ids, "start_m": head_m, "end_m": head_m,
                         "cap_start": [cap(r, "start") for r in ids], "cap_end": [cap(r, "end") for r in ids]})


def solve(roads, pairs, edits, heads, caps, auto=False, **kw):
    """The whole step: the defaults (or ``auto``: rs.auto_ends' head lengths before solving and caps after), the solve, your own on top.
    Returns (solved, the ends as drawn, the ends without yours)."""
    base = rs.auto_ends(roads, pairs) if auto else defaults(roads, pairs)
    first = ends(base, heads, caps)
    solved = rs.solve_levels(roads, pairs, edits=edits, parts=rs.casing_parts(roads, 5.0, first[["road", "start_m", "end_m"]]), **kw)
    if auto:
        base = rs.auto_ends(roads, pairs, levels=solved)
    return solved, ends(base, heads, caps), base


def write(solved, folder, ends_table):
    """levels.csv (with each edge's ends as drawn), and levels_info.json: what the solver says about it (the editor shows it without solving again)."""
    import json
    edge_levels(solved, ends_table).to_csv(Path(folder) / "levels.csv", index=False)
    info = {**solved.attrs["levels_info"], "given_up": [list(p) for p in solved.attrs["levels_given_up"]],
            "given_up_parts": [list(p) for p in solved.attrs.get("levels_given_up_parts", [])],
            "near": [list(p) for p in solved.attrs.get("levels_near", [])]}
    (Path(folder) / "levels_info.json").write_text(json.dumps(info, default=str))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--auto-ends", action="store_true", help="head lengths and caps from rs.auto_ends (at zoom 18) instead of 5 m and round")
    ap.add_argument("--max-positions", type=int, help="at most this many drawing positions (a hard bound: wishes, then stack pairs, give way)")
    a = ap.parse_args(argv)
    roads = gpd.read_parquet(a.out_dir / "roads.parquet")
    edits = a.out_dir / "edits.csv"
    heads, caps = own(a.out_dir)
    solved, drawn, _ = solve(roads, a.out_dir / "pairs.csv", edits if edits.exists() else None, heads, caps, auto=a.auto_ends,
                             max_positions=a.max_positions)
    write(solved, a.out_dir, drawn)
    info = solved.attrs["levels_info"]
    print(f"{len(roads)} roads -> {a.out_dir / 'levels.csv'}: {len(solved.attrs['levels_given_up'])} stack pair(s) given up, "
          f"{len({(u, l) for u, l, _ in solved.attrs.get('levels_near', [])})} near warning(s), "
          f"{info.get('order_violations', 0)} order wish(es) not kept, {info.get('seconds')} s")


if __name__ == "__main__":
    main()
