"""Saving the drawing order in a duckOSM file and reading it back (docs/design/levels_split_casing.md, section 11).

The numbers of ``compute_levels`` go to ``visualization.edge_levels`` (one row per ``edge_id``) and the parameters they were computed with to
``visualization.edge_levels_meta`` (one row). Both calls are explicit; reading checks the parameters and the edges and stops with a message if they differ."""
from __future__ import annotations

import hashlib

SCHEMA = "visualization"
COLS = ("casing_start", "casing_level", "casing_end", "fill_level")
_PARAMS = ("method", "head_m", "band_dist", "margin", "max_level", "band_source", "order_source", "min_positions")


def levels_params(method="solve", head_m=5.0, band_dist=10.0, margin=1.0, max_level=20, band_col=None, order="priority", min_positions=True):
    """The parameters that decide the numbers, as stored in the metadata. The names are those of ``compute_levels``; a band from the tags is ``"tags"``."""
    return {"method": method, "head_m": float(head_m), "band_dist": float(band_dist), "margin": float(margin), "max_level": int(max_level),
            "band_source": band_col or "tags", "order_source": order,
            "min_positions": True if min_positions else None}      # None: off; a file stored before the option has no value, so it reads as off


def _ids(frame):
    import numpy as np
    ids = np.asarray(frame["edge_id"]).astype("int64")
    if len(np.unique(ids)) != len(ids):
        raise ValueError("edge_id must be unique: one row per edge")
    return ids


def _hash(ids):
    import numpy as np
    return hashlib.sha256(np.sort(ids).tobytes()).hexdigest()[:32]


def save_levels(con, levels, *, schema=SCHEMA):
    """Write the result of ``compute_levels`` (a table with ``edge_id``) to ``<schema>.edge_levels`` and its parameters to ``<schema>.edge_levels_meta``,
    replacing both. ``con`` is an open, writable duckdb connection."""
    import datetime

    import pandas as pd

    from . import __version__
    params = levels.attrs.get("levels_params")
    if params is None:
        raise ValueError("save_levels needs the result of compute_levels: it carries the parameters it was computed with")
    ids = _ids(levels)
    table = pd.DataFrame({"edge_id": ids, **{c: levels[c].to_numpy().astype("int32") for c in COLS}})
    meta = pd.DataFrame([{**params, "n_edges": len(ids), "edge_hash": _hash(ids), "roadstyle_version": __version__,
                          "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}])
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for name, df in (("edge_levels", table), ("edge_levels_meta", meta)):
        con.register("_rs_levels_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {schema}.{name} AS SELECT * FROM _rs_levels_df")
        con.unregister("_rs_levels_df")


def load_levels(con, edges=None, *, schema=SCHEMA, **expect):
    """Read the stored numbers. ``expect`` are the parameters you expect, with the names and defaults of ``compute_levels``
    (``method``, ``head_m``, ``band_dist``, ``margin``, ``max_level``, ``band_col``, ``order``, ``min_positions``). If the stored parameters differ, or ``edges``
    (a table with ``edge_id``) are not exactly the edges the numbers were computed for, a ``ValueError`` says what differs; nothing is recomputed.
    Returns the table ``edge_id`` + the four columns, or, with ``edges``, a copy of ``edges`` with the four columns added."""
    import pandas as pd
    want = levels_params(**expect)
    try:
        meta = con.execute(f"SELECT * FROM {schema}.edge_levels_meta").df()
    except Exception as e:                                                  # duckdb.CatalogException: no such table
        raise ValueError(f"no {schema}.edge_levels_meta in this file: compute the levels and save them with save_levels") from e
    stored = meta.iloc[0]
    def same(a, b):
        a = None if pd.isna(a) else a
        return a == b
    diffs = [f"{k}: stored {stored.get(k)!r}, expected {want[k]!r}" for k in _PARAMS if not same(stored.get(k), want[k])]
    if diffs:
        raise ValueError(f"the stored levels were computed with other parameters ({'; '.join(diffs)}): compute them again and save them")
    table = con.execute(f"SELECT * FROM {schema}.edge_levels").df()
    if edges is None:
        return table
    ids = _ids(edges)
    if len(ids) != int(stored["n_edges"]) or _hash(ids) != stored["edge_hash"]:
        raise ValueError(f"the edges are not the edges the stored levels were computed for ({len(ids)} given, {int(stored['n_edges'])} stored, or other edge_id values): compute them again and save them")
    merged = pd.DataFrame({"edge_id": ids}).merge(table, on="edge_id", how="left")
    out = edges.copy()
    for c in COLS:
        out[c] = merged[c].to_numpy()
    out.attrs["levels_params"] = want
    return out


AREA_COLS = COLS + ("head_start_m", "head_end_m", "cap_start", "cap_end")


# a level area's own input, kept in the database too (2026-10-20), so the file holds everything: {file: (table, id columns)}
AREA_INPUTS = {"edits.csv": ("level_edits", ("a", "b")), "heads.csv": ("level_heads", ("road",)), "caps.csv": ("level_caps", ("road",))}


def _save_area_inputs(con, folder, schema):
    """edits.csv, heads.csv and caps.csv of ``folder`` as tables ``<schema>.level_edits`` / ``level_heads`` / ``level_caps``: the text as it
    is, the ids BIGINT. A file the folder does not have leaves its table as it is."""
    from pathlib import Path

    import pandas as pd
    for f, (table, ids) in AREA_INPUTS.items():
        path = Path(folder) / f
        if not path.exists():                       # the tables are the master: a folder without the file does not delete them (2026-10-20)
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        con.register("_rs_input_df", df)
        cast = ", ".join(f'CAST(NULLIF("{c}", \'\') AS BIGINT) AS "{c}"' for c in ids if c in df.columns)
        con.execute(f"CREATE OR REPLACE TABLE {schema}.{table} AS SELECT * {'REPLACE (' + cast + ')' if cast else ''} FROM _rs_input_df")
        con.unregister("_rs_input_df")


def restore_area_inputs(con, folder, *, schema=SCHEMA):
    """Write edits.csv, heads.csv and caps.csv into ``folder`` from the database, for each file the folder does not have and the database
    does. Returns the names of the files written."""
    from pathlib import Path
    have = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = ?", [schema]).fetchall()}
    written = []
    for f, (table, _) in AREA_INPUTS.items():
        path = Path(folder) / f
        if table in have and not path.exists():
            Path(folder).mkdir(parents=True, exist_ok=True)
            con.execute(f"SELECT * FROM {schema}.{table}").df().to_csv(path, index=False)
            written.append(f)
    return written


def save_area_levels(con, folder, *, schema=SCHEMA):
    """Write a level area's result (``folder``/levels.csv: the four numbers and the ends of every edge, ``roadstyle-levels solve``) to
    ``<schema>.edge_levels`` and a row saying where it came from to ``<schema>.edge_levels_meta``, replacing both, and the area's own input
    (edits.csv, heads.csv, caps.csv) to ``level_edits`` / ``level_heads`` / ``level_caps``. ``con``: a writable duckdb connection."""
    import datetime
    from pathlib import Path

    import pandas as pd

    from . import __version__
    lv = pd.read_csv(Path(folder) / "levels.csv", dtype={"edge": str})
    table = pd.DataFrame({"edge_id": lv["edge"].astype("int64"), **{c: lv[c] for c in AREA_COLS}})
    ids = _ids(table)
    meta = pd.DataFrame([{"source": "area", "area": str(Path(folder).resolve()), "n_edges": len(ids), "edge_hash": _hash(ids),
                          "roadstyle_version": __version__, "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}])
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for name, df in (("edge_levels", table), ("edge_levels_meta", meta)):
        con.register("_rs_levels_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {schema}.{name} AS SELECT * FROM _rs_levels_df")
        con.unregister("_rs_levels_df")
    _save_area_inputs(con, folder, schema)


def load_area_levels(con, edges, *, schema=SCHEMA, subset=False):
    """``edges`` (a table with ``edge_id``) with the columns of a level area's result stored by ``save_area_levels``: the four numbers and
    each edge's ends (``head_start_m``, ``head_end_m``, ``cap_start``, ``cap_end``). A ``ValueError`` if nothing is stored, if it is not from a
    level area, or if ``edges`` are not the edges it was solved for; nothing is recomputed. ``subset=True``: ``edges`` may be some of the edges it was
    solved for (a map of one mode of the file: the order was solved for all of them together); an edge it has no row for is an error."""
    import pandas as pd
    try:
        meta = con.execute(f"SELECT * FROM {schema}.edge_levels_meta").df().iloc[0]
    except Exception as e:                                                  # duckdb.CatalogException: no such table
        raise ValueError(f"no {schema}.edge_levels_meta in this file: make and solve its level area (roadstyle-levels, duckosm levels)") from e
    if meta.get("source") != "area":
        raise ValueError("the stored levels are not from a level area (an older table): make and solve its level area again")
    ids = _ids(edges)
    if subset:
        stored = set(con.execute(f"SELECT edge_id FROM {schema}.edge_levels").df()["edge_id"])
        missing = [i for i in ids if i not in stored]
        if missing:
            raise ValueError(f"{len(missing)} of the edges are not edges the stored levels were solved for (for example {missing[0]}): "
                             f"make and solve the level area again ({meta['area']})")
    elif len(ids) != int(meta["n_edges"]) or _hash(ids) != meta["edge_hash"]:
        raise ValueError(f"the edges are not the edges the stored levels were solved for ({len(ids)} given, {int(meta['n_edges'])} stored, "
                         f"or other edge_id values): make and solve the level area again ({meta['area']})")
    merged = pd.DataFrame({"edge_id": ids}).merge(con.execute(f"SELECT * FROM {schema}.edge_levels").df(), on="edge_id", how="left")
    out = edges.copy()
    for c in AREA_COLS:
        out[c] = merged[c].to_numpy()
    return out


LEVEL_KWARGS = dict(casing_start_col="casing_start", casing_level_col="casing_level", casing_end_col="casing_end", fill_level_col="fill_level",
                    head_start_m_col="head_start_m", head_end_m_col="head_end_m", cap_start_col="cap_start", cap_end_col="cap_end")


def stored_levels(db, edges, edge_id_col="edge_id"):
    """``(edges with the stored level columns, the render_edges keywords that name them)`` for ``render_edges(..., levels_db=db)``. ``db``: a duckOSM file with a level
    area (``visualization.edge_levels``); ``edges`` may be some of the edges it was solved for (a map of one mode), their ids ``int64`` or text. A ``ValueError`` says
    what is wrong: no stored levels, or an edge it has no row for."""
    import duckdb
    import pandas as pd
    con = duckdb.connect(str(db), read_only=True)
    try:
        got = load_area_levels(con, pd.DataFrame({"edge_id": edges[edge_id_col].to_numpy()}), subset=True)
    finally:
        con.close()
    out = edges.copy()
    for c in AREA_COLS:
        out[c] = got[c].to_numpy()
    return out, dict(LEVEL_KWARGS)
