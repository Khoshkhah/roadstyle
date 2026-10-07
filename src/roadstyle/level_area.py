"""A level area (docs/design/level_input.md): one folder with the solver's input, your changes and the result.

    roadstyle-levels make SOURCE FOLDER [--query SQL]   # roads.parquet + pairs.csv (written again each run); edits.csv created empty once
    roadstyle-levels solve FOLDER                       # levels.csv + levels_info.json
    roadstyle-levels edit FOLDER [--port 8780]          # the level editor, a local page

Yours, never written by ``make``: edits.csv (the overrides of the pairs), heads.csv and caps.csv (each road end's head length and cap;
an empty value: the default, 5 m and round). levels.csv has one row per edge: edge (its id), casing_start, casing_level, casing_end,
fill_level, and its ends as drawn: head_start_m, head_end_m, cap_start, cap_end; draw them with rs.render_edges(edges,
casing_start_col=..., casing_level_col=..., casing_end_col=..., fill_level_col=..., head_start_m_col=..., head_end_m_col=...,
cap_start_col=..., cap_end_col=...). In Python: make_area(edges, folder), solve_area(folder).
"""
import argparse
from pathlib import Path

import pandas as pd


def read_edges(source, query=None, geometry=None):
    """The edges of a geo file roadstyle reads, or of a .duckdb with ``query`` (a SELECT of the edges, the geometry as WKB or WKT)."""
    import roadstyle as rs

    if Path(source).suffix == ".duckdb":
        if not query:
            raise ValueError("a .duckdb source needs a query (a SELECT of the edges, the geometry as WKB or WKT)")
        import duckdb
        con = duckdb.connect(str(source), read_only=True)
        con.execute("LOAD spatial")
        return rs.from_duckdb(con, query, geometry=geometry).gdf
    return rs.load_edges(source).gdf


def make_area(edges, folder, **level_input_kw):
    """The solver's input in ``folder``: roads.parquet and pairs.csv (rs.level_input, written again each run), and an empty edits.csv the
    first time. Returns (roads, pairs)."""
    import roadstyle as rs

    roads, pairs = rs.level_input(edges, **level_input_kw)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    roads.to_parquet(folder / "roads.parquet")
    pairs.to_csv(folder / "pairs.csv", index=False)
    if not (folder / "edits.csv").exists():
        (folder / "edits.csv").write_text("relation,a,b,a_end,b_end,enabled\n")
    return roads, pairs


def solve_area(folder, auto_ends=False, max_positions=None):
    """Solve the area in ``folder`` with your edits, heads and caps; write levels.csv and levels_info.json. Returns the solved roads."""
    import geopandas as gpd

    folder = Path(folder)
    roads = gpd.read_parquet(folder / "roads.parquet")
    edits = folder / "edits.csv"
    heads, caps = own(folder)
    solved, drawn, _ = solve(roads, folder / "pairs.csv", edits if edits.exists() else None, heads, caps, auto=auto_ends,
                             max_positions=max_positions)
    write(solved, folder, drawn)
    return solved


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


def defaults(roads, pairs=None, head_m=5.0):
    """Every road end as drawn unless you set it: ``head_m`` long heads and round caps (2026-10-06: automatic heads, made for one zoom,
    were too short at the others; flat caps where two roads meet left small breaks at every joint that was not perfectly straight)."""
    return pd.DataFrame({"road": list(roads["road"]), "start_m": head_m, "end_m": head_m, "cap_start": "round", "cap_end": "round"})


def solve(roads, pairs, edits, heads, caps, auto=False, **kw):
    """The whole step: the defaults (or ``auto``: rs.auto_ends' head lengths before solving and caps after), the solve, your own on top.
    Returns (solved, the ends as drawn, the ends without yours)."""
    import roadstyle as rs

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
            "near": [list(p) for p in solved.attrs.get("levels_near", [])],
            "orders_not_kept": [list(p) for p in solved.attrs.get("levels_orders_not_kept", [])]}
    (Path(folder) / "levels_info.json").write_text(json.dumps(info, default=str))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="roadstyle-levels", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make", help="the solver's input: roads.parquet + pairs.csv (and an empty edits.csv the first time)")
    mk.add_argument("source", help="the edges: a geo file, or a .duckdb with --query")
    mk.add_argument("folder", type=Path)
    mk.add_argument("--query", help="with a .duckdb source: the SELECT of the edges")
    mk.add_argument("--geometry", help="the geometry column of --query (default: found by name)")
    mk.add_argument("--id-col", default="edge_id", help="the edges' id column (default edge_id; the row number when absent)")
    mk.add_argument("--band-col", help="the caller's bands (integers); default: the level from the layer / bridge / tunnel tags")
    mk.add_argument("--order", default="priority", help='"priority" (default), "class", or a column of numbers')
    mk.add_argument("--band-dist", type=float, default=10.0, help="metres: roads of different bands this near are over / under (default 10)")
    sv = sub.add_parser("solve", help="levels.csv from the input and your edits.csv / heads.csv / caps.csv")
    sv.add_argument("folder", type=Path)
    sv.add_argument("--auto-ends", action="store_true", help="head lengths and caps from rs.auto_ends (at zoom 18) instead of 5 m and round")
    sv.add_argument("--max-positions", type=int, help="at most this many drawing positions (a hard bound: wishes, then stack pairs, give way)")
    ed = sub.add_parser("edit", help="the level editor: a local page that writes edits.csv / heads.csv / caps.csv and solves")
    ed.add_argument("folder", type=Path)
    ed.add_argument("--port", type=int, default=8780)
    a = ap.parse_args(argv)
    if a.cmd == "make":
        edges = read_edges(a.source, a.query, a.geometry)
        roads, pairs = make_area(edges, a.folder, id_col=a.id_col, band_col=a.band_col, order=a.order, band_dist=a.band_dist)
        print(f"{len(edges)} edges -> {len(roads)} roads, {len(pairs)} pairs: "
              + ", ".join(f"{k} {v}" for k, v in pairs["relation"].value_counts().items()) + f" -> {a.folder}")
    elif a.cmd == "solve":
        solved = solve_area(a.folder, auto_ends=a.auto_ends, max_positions=a.max_positions)
        info = solved.attrs["levels_info"]
        print(f"{len(solved)} roads -> {a.folder / 'levels.csv'}: {len(solved.attrs['levels_given_up'])} stack pair(s) given up, "
              f"{len({(u, lo) for u, lo, _ in solved.attrs.get('levels_near', [])})} near warning(s), "
              f"{info.get('order_violations', 0)} order wish(es) not kept, {info.get('seconds')} s")
    else:
        from .level_editor import serve
        serve(a.folder, a.port)


if __name__ == "__main__":
    main()
