"""Fast GeoJSON FeatureCollection building — DuckDB writes the text, Python parses it once.

``json.loads(g.to_json())`` is how every backend turns styled edges into the FeatureCollection
dict it mutates and embeds — and at network scale it is the single most expensive step of a
render: GeoPandas serialises through per-feature Python objects (~20 s for Stockholm county's
456,813 edges, all columns). DuckDB's spatial extension writes the identical text in C++.

:func:`fc_dict` hands DuckDB the frame's WKB + attribute columns, emits **one feature string per
row** (a plain ``ORDER BY`` guarantees feature order; aggregating into one 300 MB string via
``to_json(list(...))`` measured 3 s slower), joins them in Python and parses once — ~6.4 s for
the county, ~3×. The parse is kept deliberately: every consumer (``bake_props``, ``_mark_lvl``,
``build_pmtiles``, the spec dict) needs real dicts, so the contract is exactly
``json.loads(gdf.to_json())`` — pinned by tests/test_fastjson.py — and ``duckdb`` stays an
optional extra: any failure falls back to GeoPandas.
"""
from __future__ import annotations

import json
import warnings
from functools import cache

__all__ = ["fc_dict"]


def fc_dict(gdf) -> dict:
    """The parsed-GeoJSON FeatureCollection for a GeoDataFrame.

    Drop-in replacement for ``json.loads(gdf.to_json())`` — same features, same ids
    (``str(index)``), same nulls, same coordinate values — just built by DuckDB when available.
    """
    try:
        return _duckdb_fc(gdf)
    except ImportError:                      # duckdb is an optional extra — quiet fallback
        return json.loads(gdf.to_json())
    except Exception as e:                   # never let the fast path break a render
        warnings.warn(f"fast GeoJSON emit fell back to GeoPandas: {e!r}",
                      RuntimeWarning, stacklevel=2)
        return json.loads(gdf.to_json())


@cache
def _con():
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    return con


def _q_ident(c) -> str:
    return '"' + str(c).replace('"', '""') + '"'


def _q_lit(c) -> str:
    return "'" + str(c).replace("'", "''") + "'"


def _duckdb_fc(gdf) -> dict:
    import pandas as pd

    df = pd.DataFrame(gdf.drop(columns=[gdf.geometry.name]))
    cols = list(df.columns)
    if any(str(c).startswith("__rs_fc_") for c in cols):   # helper-column collision → fallback
        raise ValueError("reserved __rs_fc_* column present")
    for c in cols:
        # float32 -> float64 first: GeoPandas emits float(np.float32(x)) (94.2f becomes
        # 94.19999694824219); DuckDB would print the shorter REAL repr and parse different.
        if str(df[c].dtype) == "float32":
            df[c] = df[c].astype("float64")
    wkb = gdf.geometry.to_wkb()
    # GeoPandas emits "geometry": null for missing AND empty geometries; ST_AsGeoJSON would
    # write {"type":...,"coordinates":[]} for empty ones — null the WKB so COALESCE below
    # lands on JSON null for both (surfaced by duckmap building layers that simplify to empty).
    empty = gdf.geometry.is_empty | gdf.geometry.isna()
    if empty.any():
        wkb = wkb.where(~empty, None)
    df["__rs_fc_wkb"] = wkb
    df["__rs_fc_id"] = gdf.index.astype(str)               # to_json: feature id = str(index)
    df["__rs_fc_i"] = range(len(df))

    props = ", ".join(f"{_q_lit(c)}, {_q_ident(c)}" for c in cols)
    con = _con()
    con.register("__rs_fc_frame", df)
    try:
        rows = con.execute(f"""
            SELECT CAST(json_object(
                'id', "__rs_fc_id",
                'type', 'Feature',
                'properties', json_object({props}),
                'geometry', COALESCE(CAST(ST_AsGeoJSON(ST_GeomFromWKB("__rs_fc_wkb")) AS JSON),
                                     CAST('null' AS JSON))
            ) AS VARCHAR)
            FROM __rs_fc_frame ORDER BY "__rs_fc_i"
        """).fetchall()
    finally:
        con.unregister("__rs_fc_frame")
    feats = ",".join(r[0] for r in rows)
    return json.loads('{"type":"FeatureCollection","features":[' + feats + "]}")
