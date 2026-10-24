"""A duckOSM file as the Rust engine's input (the mapstyle merge): the roads of every mode with their stored levels and the base map's
tables (``features.*``), read with the SQL of the Rust engine (``roadstyle_io::duckosm``: the one copy, which the browser runs too) on a
DuckDB connection of this process. The outputs are the engine's input files, as GeoParquet bytes."""
from __future__ import annotations

import io
import json
import tempfile
import warnings
from pathlib import Path


def layer_specs() -> list[dict]:
    """The base map's layers (data/basemap/layers.yaml), in draw order."""
    from importlib.resources import files

    import yaml
    return yaml.safe_load(files("roadstyle").joinpath("data/basemap/layers.yaml").read_text(encoding="utf-8"))["layers"]


def read(db, mode: str = "all", *, levels: str = "stored", layers: bool = True, only: bool = False):
    """``(roads, features, levels_kw)`` of the duckOSM file ``db`` for the map of ``mode`` ("all", "driving", "walking" or "cycling"):
    the roads (GeoParquet bytes), the base map's rows (GeoParquet bytes, None with ``layers=False`` or when the file has none) and the
    look's keyword ``levels``: the stored levels' check ({edge_hash, n_edges}) with ``levels="stored"``, or "tags" (the engine computes
    the levels with the tags rule). A base-map layer whose table or query fails is skipped, as mapstyle's load_layers does. ``only``:
    the roads of ``mode`` alone (its edges and private_edges; render_map(only=True)); the stored levels were solved for every mode
    together, so each of these roads must have its stored row (load_area_levels(subset=True))."""
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
        plan = json.loads(r.duckosm_plan(tables, columns, mode, levels == "tags", json.dumps(layer_specs() if layers else []), only))
        if plan["roads"] is None:
            raise ValueError(f"{db}: {plan['roads_error']}")
        e, rows, drop = plan["roads"]
        con.execute(e)
        if plan["meta"]:
            try:
                row = con.execute(plan["meta"]).fetchone()
            except duckdb.CatalogException:
                row = None
        else:
            row = None
        con.execute(rows)
        if plan["subset"]:                                  # the map of one mode: each road has its stored row
            missing_sql, ids_sql = plan["subset"]
            missing, example = con.execute(missing_sql).fetchone()
            ids = [x[0] for x in con.execute(ids_sql).fetchall()]
            level_kw = json.loads(r.duckosm_subset_levels(tuple(row) if row else None, missing, example, ids))
        elif plan["meta"]:
            level_kw = json.loads(r.duckosm_levels(tuple(row) if row else None))
        else:
            level_kw = "tags"
        con.execute(drop)
        made = []
        for lyr in plan["layers"]:
            for k, sql in enumerate(lyr["sql"]):          # mapstyle's query, then its fallback (no tags: the height of the kind)
                try:
                    con.execute(f"CREATE OR REPLACE TEMP TABLE f{lyr['spec']} AS {sql}")
                except duckdb.Error as e:
                    if k == len(lyr["sql"]) - 1:
                        warnings.warn(f"{db}: base-map layer {lyr['name']} skipped: {e}", stacklevel=2)
                    continue
                if k:
                    warnings.warn(f"{db}: base-map layer {lyr['name']}: no tags column (an older file): the heights of the kinds", stacklevel=2)
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

    return rust().resolve_look(json.dumps(_options(db, mode, theme, paths, levels, kwargs)))


def _options(db, mode, theme, paths, levels, kwargs) -> dict:
    """The look's options of a duckOSM map (`look`): the base map's, and the map options."""
    args = {**kwargs, **({"levels": levels} if levels is not None else {})}
    return {"base_map": {"mode": mode, "theme": theme, "paths": paths, "place": Path(db).stem}, "args": args}


def export_inline(db, mode: str = "all", *, theme: str = "osm", paths: str = "google", layers: bool = True, levels: str = "stored",
                  only: bool = False, **kwargs) -> dict:
    """mapstyle's ``export_inline`` on the Rust engine: the map of the duckOSM file ``db`` (its roads in the style of ``mode``, the
    base map of ``features.*`` with ``layers``) as one style with the data in it, for an app that draws a MapLibre style (the roadstyle
    GeoLibre plugin). ``only``: the roads of ``mode`` alone (``read``). ``kwargs``: render_edges' keywords (``view_3d`` is on, as
    export_inline's)."""
    from ._engine import _warn, rust

    roads, features, level_kw = read(db, mode, levels=levels, layers=layers, only=only)
    lk = look(db, mode, theme=theme, paths=paths, levels=level_kw, **{"view_3d": True, "export": True, **kwargs})
    style = json.loads(rust().make_style(roads, lk, features, None, None))
    _warn()
    return style


def page(db, mode: str = "all", *, theme: str = "osm", paths: str = "google", layers: bool = True, levels: str = "stored",
         only: bool = False, interaction: dict = None, dashboard: bool = False, **kwargs):
    """mapstyle's ``render_map`` on the Rust engine: the page of the duckOSM file ``db`` (``read``, its roads in the style of ``mode``, the
    base map of ``features.*`` with ``layers``, the shared dashboard with the base map's controls: modes, kinds, each layer's clicks,
    tooltip and popup). ``interaction``: a layer's start ``{clickable, tooltip, popup}`` (e.g. ``{"landcover": {"clickable": True}}``).
    ``dashboard=True``: roadstyle's report page (``sidebar="report"``). ``kwargs``: render_edges' keywords (``basemap``, ``tiles``,
    ``sidebar``, ...). Gives a ``WebMap`` (``.save(path)``)."""
    from . import render_web as rw
    from ._engine import _warn, page_given, rust

    if kwargs.get("planner"):
        raise ValueError("duckosm.page has no route planner yet: use mapstyle's render_map(planner=True)")
    roads, features, level_kw = read(db, mode, levels=levels, layers=layers, only=only)
    kw = {**kwargs, "state": "live", **({"interaction": interaction} if interaction else {})}
    if dashboard:
        from importlib.resources import files

        import yaml
        roads = _with_modes(roads)
        colors = yaml.safe_load(files("roadstyle").joinpath("data/basemap/modes.yaml").read_text(encoding="utf-8"))["mode_colors"]
        # the panel shows the clicked road: no road hover tooltip
        kw = {"name": f"{Path(db).stem}: dashboard", "tooltip": None, "sidebar": "report",
              "color_options": {"Road class": {}, "Modes": {"color_by": "modes", "colors": colors}}, **kw}
    o = _options(db, mode, theme, paths, level_kw, kw)
    lk = rust().resolve_look(json.dumps(o))
    # the look's base maps (blank, in the theme's land colour, and the switcher's), where the caller gives none: the keys that Python resolves
    args = json.loads(lk.part("args"))
    given = page_given({**{k: args.get(k) for k in ("basemap", "basemaps")}, **kw})
    html = rust().page_from(roads, lk, json.dumps(o), json.dumps(given), features)
    _warn()
    return rw.WebMap(html)


def _with_modes(roads: bytes) -> bytes:
    """The roads (GeoParquet bytes) with the column ``modes``: the modes that can use each road, as the dashboard's colour option
    "Modes" names them ("all modes", "driving + walking", ...; mapstyle's render_map(dashboard=True)).
    ponytail: Python only; a JavaScript host's dashboard gets the column when the reader's SQL writes it."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    modes = ("driving", "walking", "cycling")
    t = pq.read_table(io.BytesIO(roads))
    flags = [t.column(m).to_pylist() for m in modes]
    labels = ["all modes" if all(f) else " + ".join(m for m, x in zip(modes, f, strict=True) if x) for f in zip(*flags, strict=True)]
    out = io.BytesIO()
    pq.write_table(t.append_column("modes", pa.array(labels, pa.string())), out)
    return out.getvalue()


def export_style(db, out_dir, *, base_url: str, mode: str = "all", theme: str = "osm", paths: str = "google", layers: bool = True,
                 levels: str = "stored", format: str = "xyz", only: bool = False, **kwargs):
    """mapstyle's ``export_style`` on the Rust engine: the map of the duckOSM file ``db`` as style.json, its vector tiles (the roads
    and the base map; ``format``: "xyz" or "pmtiles"), the sprite and the popup's files in ``out_dir``, served at ``base_url``, for an
    app that draws a MapLibre style (GeoLibre, RustGIS, QGIS). ``only``: the roads of ``mode`` alone (``read``). The path of style.json."""
    import pyarrow.parquet as pq
    import shapely

    from ._engine import _warn, _write_export, rust

    if format not in ("xyz", "pmtiles"):
        raise ValueError(f"format must be 'xyz' or 'pmtiles', got {format!r}")
    roads, features, level_kw = read(db, mode, levels=levels, layers=layers, only=only)
    lk = look(db, mode, theme=theme, paths=paths, levels=level_kw, **{"view_3d": True, "export": True, "tiles": True, **kwargs})
    table = pq.read_table(io.BytesIO(roads))
    keep = [c for c in table.column_names if c != "geometry"]          # every column: a click shows the data
    t = rust().Tiler(roads, lk, features, None, "", keep)
    _warn()
    bounds = tuple(float(v) for v in shapely.total_bounds(shapely.from_wkb(table.column("geometry").to_numpy(zero_copy_only=False))))
    return _write_export(t, out_dir, base_url, format, json.loads(lk.part("args"))["name"], bounds)


def base_map(mode: str = "all", *, theme: str = "osm", paths: str = "google") -> dict:
    """The base map's look of one choice (roadstyle-look's basemap.rs; mapstyle's mode_settings and styles): {"palette": the roads'
    palette name, "settings": its settings source, "features": the base map's part of the look (its layers, 3D heights, style and
    images), "args": the mode's map options}."""
    from ._engine import rust

    lk = rust().resolve_look(json.dumps({"base_map": {"mode": mode, "theme": theme, "paths": paths}}))
    return {k: json.loads(lk.part(k)) for k in ("palette", "settings", "features", "args")}


def theme(name: str = "osm"):
    """``(style, file, transform)`` of a base map's theme: osm_carto.yaml in the theme's colours, the theme file ({} for "osm") and its
    transform (saturation, lighten), for ``recolor``."""
    from ._engine import rust

    style, file, transform = json.loads(rust().base_map_theme(name))
    return style, file, tuple(transform)


def recolor(colour, transform):
    """A "#rrggbb" colour in a theme's colours (``transform``: theme()'s third value); any other value as it is."""
    from ._engine import rust

    return json.loads(rust().base_map_recolor(json.dumps(colour), *transform))
