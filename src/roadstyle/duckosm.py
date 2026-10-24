"""A duckOSM file as the Rust engine's input (the mapstyle merge): the roads of every mode with their stored levels and the base map's
tables (``features.*``), read with the SQL of the Rust engine (``roadstyle_io::duckosm``: the one copy, which the browser runs too) on a
DuckDB connection of this process. The outputs are the engine's input files, as GeoParquet bytes."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path


def layer_specs() -> list[dict]:
    """The base map's layers (data/basemap/layers.yaml), in draw order."""
    from importlib.resources import files

    import yaml
    return yaml.safe_load(files("roadstyle").joinpath("data/basemap/layers.yaml").read_text(encoding="utf-8"))["layers"]


def read(db, mode: str = "all", *, levels: str = "stored", layers: bool = True):
    """``(roads, features, levels_kw)`` of the duckOSM file ``db`` for the map of ``mode`` ("all", "driving", "walking" or "cycling"):
    the roads (GeoParquet bytes), the base map's rows (GeoParquet bytes, None with ``layers=False`` or when the file has none) and the
    look's keyword ``levels``: the stored levels' check ({edge_hash, n_edges}) with ``levels="stored"``, or "tags" (the engine computes
    the levels with the tags rule). A base-map layer whose table or query fails is skipped, as mapstyle's load_layers does."""
    import duckdb

    from ._engine import rust

    if levels not in ("stored", "tags"):
        raise ValueError(f'levels must be "stored" or "tags", got {levels!r}')
    r = rust()
    con = duckdb.connect(str(db), read_only=True)
    try:
        catalog = con.execute("SELECT current_database()").fetchone()[0]
        tq, cq = r.duckosm_catalog_sql(catalog)
        tables, columns = con.execute(tq).fetchall(), con.execute(cq).fetchall()
        plan = json.loads(r.duckosm_plan(tables, columns, mode, levels == "tags", json.dumps(layer_specs() if layers else [])))
        e, rows, drop = plan["roads"]
        con.execute(e)
        if plan["meta"]:
            try:
                row = con.execute(plan["meta"]).fetchone()
            except duckdb.CatalogException:
                row = None
            level_kw = json.loads(r.duckosm_levels(tuple(row) if row else None))
        else:
            level_kw = "tags"
        con.execute(rows)
        con.execute(drop)
        made = []
        for lyr in plan["layers"]:
            for sql in dict.fromkeys((lyr["with_tags"], lyr["without_tags"])):       # an older file has no tags: the height of the kind
                try:
                    con.execute(f"CREATE OR REPLACE TEMP TABLE f{lyr['spec']} AS {sql}")
                    made.append(lyr["spec"])
                    break
                except duckdb.Error:
                    continue
        with tempfile.TemporaryDirectory() as d:
            def parquet(select, name):
                p = Path(d) / name
                con.execute(f"COPY ({select}) TO '{p}' (FORMAT parquet)")
                return p.read_bytes()
            roads = parquet(plan["select"], "roads.parquet")
            fsel = r.duckosm_features_select(made)
            features = parquet(fsel, "features.parquet") if fsel else None
    finally:
        con.close()
    return roads, features, level_kw
