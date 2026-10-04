"""Saving the drawing order in a duckOSM file and reading it back (docs/design/levels_split_casing.md, section 11).

The numbers of ``compute_levels`` go to ``visualization.edge_levels`` (one row per ``edge_id``) and the parameters they were computed with to
``visualization.edge_levels_meta`` (one row). Both calls are explicit; reading checks the parameters and the edges and stops with a message if they differ."""
from __future__ import annotations

import hashlib

SCHEMA = "visualization"
COLS = ("casing_start", "casing_level", "casing_end", "fill_level")
_PARAMS = ("method", "head_m", "band_dist", "margin", "max_level", "band_source", "order_source", "min_positions")


def levels_params(method="solve", head_m=5.0, band_dist=10.0, margin=1.0, max_level=20, band_col=None, order=None, min_positions=True):
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
