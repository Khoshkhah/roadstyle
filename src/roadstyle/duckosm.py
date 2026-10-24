"""A duckOSM file as the Rust engine's input (the mapstyle merge): the roads of every mode with their stored levels and the base map's
tables (``features.*``), read with the SQL of the Rust engine (``roadstyle_io::duckosm``: the one copy, which the browser runs too) on a
DuckDB connection of this process. The outputs are the engine's input files, as GeoParquet bytes."""
from __future__ import annotations

import json
import tempfile
import warnings
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
        if plan["layers"]:
            try:                     # the background's land without the sea needs the spatial extension (load_layers' _spatial)
                for sql in plan["spatial"]:
                    con.execute(sql)
            except duckdb.Error as e:
                warnings.warn(f"{db}: no spatial extension of DuckDB ({e}): the background is the whole boundary", stacklevel=2)
        for lyr in plan["layers"]:
            for k, sql in enumerate(lyr["sql"]):          # mapstyle's query, then its fallbacks (no tags: the height of the kind; no spatial)
                try:
                    con.execute(f"CREATE OR REPLACE TEMP TABLE f{lyr['spec']} AS {sql}")
                except duckdb.Error as e:
                    if k == len(lyr["sql"]) - 1:
                        warnings.warn(f"{db}: base-map layer {lyr['name']} skipped: {e}", stacklevel=2)
                    continue
                if k:
                    warnings.warn(f"{db}: base-map layer {lyr['name']}: query {k + 1} of {len(lyr['sql'])} (an older file, or no spatial extension)",
                                  stacklevel=2)
                made.append(lyr["spec"])
                break
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


def look(db, mode: str = "all", *, theme: str = "osm", paths: str = "google", levels=None, **kwargs):
    """The look of the map of the duckOSM file ``db`` (the Rust engine's ``Look``): the base map's look of ``mode``, ``theme`` and
    ``paths`` (mapstyle's mode_settings and styles), render_map's map options (the name from the file's name, the tooltip, the reader's
    columns, the stored levels' columns with ``levels``), and ``kwargs`` over them (render_edges' keywords)."""
    from ._engine import rust

    args = {**kwargs, **({"levels": levels} if levels is not None else {})}
    o = {"base_map": {"mode": mode, "theme": theme, "paths": paths, "place": Path(db).stem}, "args": args}
    return rust().resolve_look(json.dumps(o))


def export_inline(db, mode: str = "all", *, theme: str = "osm", paths: str = "google", layers: bool = True, levels: str = "stored",
                  **kwargs) -> dict:
    """mapstyle's ``export_inline`` on the Rust engine: the map of the duckOSM file ``db`` (its roads in the style of ``mode``, the
    base map of ``features.*`` with ``layers``) as one style with the data in it, for an app that draws a MapLibre style (the roadstyle
    GeoLibre plugin). ``kwargs``: render_edges' keywords (``view_3d`` is on, as export_inline's)."""
    from ._engine import _warn, rust

    roads, features, level_kw = read(db, mode, levels=levels, layers=layers)
    lk = look(db, mode, theme=theme, paths=paths, levels=level_kw, **{"view_3d": True, "export": True, **kwargs})
    style = json.loads(rust().make_style(roads, lk, features, None, None))
    _warn()
    return style
