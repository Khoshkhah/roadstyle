"""A level area (docs/design/level_input.md): one folder with the solver's input, your changes and the result.

    roadstyle-levels make SOURCE FOLDER [--query SQL]   # roads.parquet + pairs.csv (written again each run, a stack's parts with heads.csv's
                                                        # heads); edits.csv created empty once
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


IDS = ("road", "edges", "reversed")      # roads.parquet's id columns: Int64 in the file, text in memory (read_roads)


def read_roads(folder):
    """roads.parquet of the area in ``folder``, its ids (``road``, ``edges``, ``reversed``) as text, as rs.level_input gives them. The
    file has them as Int64 (duckOSM's BIGINT edge ids); an area made before has text, which stays text."""
    import geopandas as gpd

    roads = gpd.read_parquet(Path(folder) / "roads.parquet")
    txt = lambda v: None if v is None else str(v)                                       # noqa: E731
    roads["road"] = [txt(v) for v in roads["road"].astype(object)]
    for c in ("edges", "reversed"):
        roads[c] = [[str(e) for e in v] for v in roads[c]]
    return roads


def write_roads(roads, path):
    """rs.level_input's roads as roads.parquet: the ids as Int64 when each is a whole number (the BIGINT rule), else as text (an
    id column of text, which only the Python engine takes). In memory, level_input keeps them as text: duckosm-rust/tools compares
    them as text (a frozen repo)."""
    whole = lambda v: str(v).lstrip("-").isdigit()                                       # noqa: E731
    out = roads.copy()
    if all(whole(r) for r in out["road"]) and all(whole(e) for c in ("edges", "reversed") for v in out[c] for e in v):
        out["road"] = pd.array([int(r) for r in out["road"]], dtype="Int64")
        for c in ("edges", "reversed"):
            out[c] = [[int(e) for e in v] for v in out[c]]
    out.to_parquet(path)


def make_area(edges, folder, db=None, engine=None, **level_input_kw):
    """The solver's input in ``folder``: roads.parquet and pairs.csv (rs.level_input, written again each run), and an empty edits.csv the
    first time. Which parts of a stack's upper road cross the road under it is decided here, once, with the heads of the folder's heads.csv
    if there is one (else 5 m): a head changed later never needs a solve (2026-10-08). With ``db`` (a .duckdb file), the area belongs to it (area.json): every solve also writes the result into it
    (``visualization.edge_levels``, rs.save_area_levels), the editor's too, and your edits.csv / heads.csv / caps.csv go into it as
    ``visualization.level_edits`` / ``level_heads`` / ``level_caps``; a file the folder does not have is written from there first. Returns
    (roads, pairs)."""
    import roadstyle as rs

    folder = Path(folder)
    if db is not None:                                  # a new folder of a database: your edits, heads and caps from the database
        import duckdb

        import roadstyle as rs
        con = duckdb.connect(str(db), read_only=True)
        try:
            con.execute("INSTALL spatial; LOAD spatial;")  # a duckOSM file has geometry columns
            got = rs.restore_area_inputs(con, folder)
        finally:
            con.close()
        if got:
            print(f"{', '.join(got)}: written from {db} (visualization.level_*)", flush=True)
    from . import _engine
    if _engine.engine(engine) == "rust":                 # ``engine``: "python" or "rust" (ROADSTYLE_ENGINE): roadstyle::level_area in Rust
        import warnings

        kw = {k: v for k, v in level_input_kw.items() if v is not None or k in ("band_col", "order")}
        if "id_col" in level_input_kw and not level_input_kw["id_col"]:
            kw["id_col"] = ""                           # no id column: the row numbers, as level_input
        if kw.pop("heads", None) is not None:
            raise ValueError("engine='rust': make_area reads the folder's heads.csv; heads= is in the Python engine only")
        if edges.crs is not None and edges.crs.to_epsg() != 4326:      # Rust reads longitude and latitude
            edges = edges.to_crs(4326)
        _, _, said = _engine.rust().make_area(_engine._arrow(edges), str(folder), **kw)
        for w in said:
            warnings.warn(w, stacklevel=2)
        roads, pairs = read_roads(folder), pd.read_csv(folder / "pairs.csv", dtype=str, keep_default_na=False)
    else:
        if (folder / "heads.csv").exists():
            level_input_kw.setdefault("heads", folder / "heads.csv")
        roads, pairs = rs.level_input(edges, **level_input_kw)
        folder.mkdir(parents=True, exist_ok=True)
        write_roads(roads, folder / "roads.parquet")
        pairs.to_csv(folder / "pairs.csv", index=False)
        if not (folder / "edits.csv").exists():
            (folder / "edits.csv").write_text("relation,a,b,a_end,b_end,enabled\n")
    if db is not None:
        import json
        import os
        (folder / "area.json").write_text(json.dumps({"db": os.path.relpath(Path(db).resolve(), folder.resolve())}))
    return roads, pairs


def area_db(folder):
    """The .duckdb file the area in ``folder`` belongs to (area.json), or None."""
    import json
    f = Path(folder) / "area.json"
    return (Path(folder) / json.loads(f.read_text())["db"]).resolve() if f.exists() else None


def solve_area(folder, auto_ends=False, max_positions=None, engine=None):
    """Solve the area in ``folder`` with your edits, heads and caps; write levels.csv and levels_info.json. Returns the solved roads.
    ``engine``: the solver of solve_levels ("python" or "rust"; default ROADSTYLE_ENGINE, else Python)."""
    folder = Path(folder)
    roads = read_roads(folder)
    edits = folder / "edits.csv"
    heads, caps = own(folder, roads)
    solved, drawn, _ = solve(roads, folder / "pairs.csv", edits if edits.exists() else None, heads, caps, auto=auto_ends,
                             max_positions=max_positions, engine=engine)
    write(solved, folder, drawn)
    return solved


def edge_levels(solved, ends_table):
    """One row per edge from one row per road (and its ends as drawn): an edge running the other way has its two heads and caps swapped."""
    e = {r: v for r, *v in ends_table[["road", "start_m", "end_m", "cap_start", "cap_end"]].itertuples(index=False)}   # a dict: .loc per road took seconds
    rows = []
    for r in solved.itertuples():
        hs, he, cs, ce = e[r.road]
        for x in r.edges:
            rows.append((x, r.casing_start, r.casing_level, r.casing_end, r.fill_level, hs, he, cs, ce))
        for x in r.reversed:
            rows.append((x, r.casing_end, r.casing_level, r.casing_start, r.fill_level, he, hs, ce, cs))
    return pd.DataFrame(rows, columns=["edge", "casing_start", "casing_level", "casing_end", "fill_level", "head_start_m", "head_end_m", "cap_start", "cap_end"])


def own(folder, roads):
    """Your own head lengths and caps: heads.csv / caps.csv as {road: (start, end)} ("" = the automatic one). A row may name any edge of a
    road, as edits.csv does: an edge running against its road has its start and end swapped. A row naming no road of ``roads`` is an error."""
    side = {str(r): (str(r), False) for r in roads["road"]}
    for r, fw, bw in zip(roads["road"], roads["edges"], roads["reversed"], strict=True):
        side.update({str(x): (str(r), False) for x in fw} | {str(x): (str(r), True) for x in bw})

    def read(path, cols):
        if not path.exists():
            return {}
        f = pd.read_csv(path, dtype=str, keep_default_na=False)
        if "cap" in f and "start" not in f:                     # an older caps.csv: one value for both ends
            f["start"] = f["end"] = f["cap"]
        if cols[0] not in f:                                    # older still: only the roads, flat
            f[cols[0]] = f[cols[1]] = "flat"
        unknown = [r for r in f["road"] if r not in side]
        if unknown:
            raise ValueError(f"{path}: {len(unknown)} row(s) name no road of this area (first: {unknown[:5]})")
        out = {}
        for r, s, e in zip(f["road"], f[cols[0]], f[cols[1]], strict=True):
            road, rev = side[r]
            v = (e, s) if rev else (s, e)
            if out.get(road, v) != v:
                raise ValueError(f"{path}: two rows for road {road} (by its two directions) disagree: {out[road]} and {v}")
            out[road] = v
        return out
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


def defaults(roads, pairs, head_m=5.0):
    """Every road end as drawn unless you set it: ``head_m`` long heads and round caps, square at a two-way road's dead end (2026-10-06: automatic heads, made for one zoom,
    were too short at the others; flat caps where two roads meet left small breaks at every joint that was not perfectly straight)."""
    from .levels import dead_end_cap
    dead = dead_end_cap(roads, pairs)      # a two-way road's dead end is square, see dead_end_cap
    n = len(roads)
    return pd.DataFrame({"road": list(roads["road"]), "start_m": head_m, "end_m": head_m,
                         "cap_start": [dead.get((i, "start"), "round") for i in range(n)], "cap_end": [dead.get((i, "end"), "round") for i in range(n)]})


def solve(roads, pairs, edits, heads, caps, auto=False, **kw):
    """The whole step: the solve (from the tables only), and the ends as drawn: the defaults (or ``auto``: rs.auto_ends' head lengths and
    caps, the caps from the solved levels), your own on top. Returns (solved, the ends as drawn, the ends without yours)."""
    import roadstyle as rs

    base = defaults(roads, pairs)
    solved = rs.solve_levels(roads, pairs, edits=edits, **kw)
    if auto:
        base = rs.auto_ends(roads, pairs, levels=solved)
    return solved, ends(base, heads, caps), base


LEVELS = ["casing_start", "casing_level", "casing_end", "fill_level"]




def _keep_fixed(local, fixed):
    """Shift the local result as a whole so the ``fixed`` roads keep exactly their numbers (2026-10-08): the solver puts its ground (the
    most common main casing number) at 0, so a local result can come back shifted by k, and every road would look changed. The fixed roads
    all agree on one k; when they do not, the solver did not hold them, and that is an error."""
    now = dict(zip(local["road"], zip(*(local[c].tolist() for c in LEVELS), strict=True), strict=True))
    shifts = {b - a for r, v in fixed.items() for a, b in zip(now[r], v, strict=True)}
    if len(shifts) > 1:
        raise RuntimeError(f"solve_local: the fixed roads moved by different amounts ({sorted(shifts)}): the solver did not hold them")
    if shifts and (k := shifts.pop()):
        for c in LEVELS:
            local[c] = local[c] + k


def _worse(local, previous):
    """Why the local result ``local`` cannot stand for the whole solve (None: it can): a crossing given up that ``previous`` kept (or did not
    have), more order wishes not kept or near warnings than ``previous`` (counts: the solver trades one for another as the whole solve may).
    More drawing positions do not count (2026-10-08): in simple mode a position is only a sort number in the one road layer."""
    new = {tuple(p) for p in local.attrs["levels_given_up_parts"]} - {tuple(p) for p in previous.attrs.get("levels_given_up_parts", [])}
    if new:
        return f"{len(new)} crossing part(s) given up that were kept (first: {' '.join(sorted(new)[0])})"
    for k, what in (("levels_orders_not_kept", "order wishes not kept"), ("levels_near", "near warnings")):
        n, m = len(local.attrs[k]), len(previous.attrs.get(k, []))
        if n > m:
            return f"{n} {what}, {m} before"
    return None


def write(solved, folder, ends_table):
    """levels.csv (with each edge's ends as drawn), and levels_info.json: what the solver says about it (the editor shows it without solving again)."""
    import json
    edge_levels(solved, ends_table).to_csv(Path(folder) / "levels.csv", index=False)
    info = {**solved.attrs["levels_info"], "given_up": [list(p) for p in solved.attrs["levels_given_up"]],
            "given_up_parts": [list(p) for p in solved.attrs.get("levels_given_up_parts", [])],
            "near": [list(p) for p in solved.attrs.get("levels_near", [])],
            "orders_not_kept": [list(p) for p in solved.attrs.get("levels_orders_not_kept", [])]}
    (Path(folder) / "levels_info.json").write_text(json.dumps(info, default=str))
    db = area_db(folder)
    if db is not None:                                  # the area of a database: the result goes into it too
        import duckdb

        import roadstyle as rs
        con = duckdb.connect(str(db))
        try:
            con.execute("INSTALL spatial; LOAD spatial;")  # a duckOSM file has spatial indexes: writing it needs the extension
            rs.save_area_levels(con, folder)
            con.execute("CHECKPOINT")
        finally:
            con.close()


def serve_rust(folder, port=8780):
    """The level editor in Rust: the solver runs in the page, and the Rust server (roadstyle-serve, in the extension with the
    editor's page files) gives it the area's files and saves your changes. Waits until Ctrl+C."""
    import time

    from ._engine import rust
    if not (Path(folder) / "roads.parquet").exists():
        raise ValueError(f"{folder}: no roads.parquet: make the area first (roadstyle-levels make)")
    rust().serve(str(Path(folder).resolve()), port)
    print(f"level editor: http://127.0.0.1:{port}/level_editor/  ({folder}; Ctrl+C to stop)", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


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
    mk.add_argument("--near-rules", action="store_true", help="also write the parts that only come near the road under them (near rows: lifted last; slower, more positions)")
    mk.add_argument("--engine", choices=["python", "rust"], default="rust", help="rust (default): roadstyle::level_area; python: level_input")
    sv = sub.add_parser("solve", help="levels.csv from the input and your edits.csv / heads.csv / caps.csv")
    sv.add_argument("folder", type=Path)
    sv.add_argument("--auto-ends", action="store_true", help="head lengths and caps from rs.auto_ends (at zoom 18) instead of 5 m and round")
    sv.add_argument("--max-positions", type=int, help="at most this many drawing positions (a hard bound: wishes, then stack pairs, give way)")
    ed = sub.add_parser("edit", help="the level editor: a local page that writes edits.csv / heads.csv / caps.csv and solves")
    ed.add_argument("folder", type=Path)
    ed.add_argument("--port", type=int, default=8780)
    sv.add_argument("--engine", choices=["python", "rust"], help="the solver (default: ROADSTYLE_ENGINE, else python); rust: a "
                                                                  "minimum-cost flow, no time limit, no --max-positions")
    a = ap.parse_args(argv)
    if a.cmd == "make":
        edges = read_edges(a.source, a.query, a.geometry)
        roads, pairs = make_area(edges, a.folder, engine=a.engine, id_col=a.id_col, band_col=a.band_col, order=a.order, band_dist=a.band_dist,
                                  near_rules=a.near_rules)
        print(f"{len(edges)} edges -> {len(roads)} roads, {len(pairs)} pairs: "
              + ", ".join(f"{k} {v}" for k, v in pairs["relation"].value_counts().items()) + f" -> {a.folder}")
    elif a.cmd == "solve":
        solved = solve_area(a.folder, auto_ends=a.auto_ends, max_positions=a.max_positions, engine=a.engine)
        info = solved.attrs["levels_info"]
        print(f"{len(solved)} roads -> {a.folder / 'levels.csv'}: {len(solved.attrs['levels_given_up'])} stack pair(s) given up, "
              f"{len({(u, lo) for u, lo, _ in solved.attrs.get('levels_near', [])})} near warning(s), "
              f"{info.get('order_violations', 0)} order wish(es) not kept, {info.get('seconds')} s")
    else:
        serve_rust(a.folder, a.port)


if __name__ == "__main__":
    main()
