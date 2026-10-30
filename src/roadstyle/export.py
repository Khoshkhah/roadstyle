"""The roads as a MapLibre style and vector tiles, for other apps (docs/design/style_export.md).

``export_style`` writes ``style.json``, the tiles (a ``tiles/{z}/{x}/{y}.pbf`` folder, or one ``roads.pmtiles``) and a
sprite with the one-way arrow. GeoLibre, RustGIS, QGIS and any MapLibre page open the style by its URL. The style is
the one ``render_edges(..., tiles=True)`` puts in its page; what the page's JavaScript does (popups, the rs* API, the
controls, Street View, Google 3D) is not in it.

"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from . import _assets


def _camera(bounds, width=1024, height=768):
    """``(center, zoom)`` that fits ``bounds`` (lon/lat) in a ``width`` x ``height`` px view, as the page's fitBounds."""
    minx, miny, maxx, maxy = bounds
    def y(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(max(-85.0, min(85.0, lat))) / 2))
    zx = math.log2(width / 256 * 360 / max(maxx - minx, 1e-9))
    zy = math.log2(height / 256 * 2 * math.pi / max(y(maxy) - y(miny), 1e-9))
    return [(minx + maxx) / 2, (miny + maxy) / 2], round(max(0.0, min(18.0, min(zx, zy))), 2)


_LEVEL_COLS = {"casing_level_col": "casing_level", "fill_level_col": "fill_level", "casing_start_col": "casing_start",
               "casing_end_col": "casing_end", "head_start_m_col": "head_start_m", "head_end_m_col": "head_end_m",
               "cap_start_col": "cap_start", "cap_end_col": "cap_end"}


def export_geojson(edges, out_dir, *, format: str = "geojson", keep=None, **kwargs) -> dict:
    """Stage 1 of the Rust engine (docs/rust/architecture.md, "The three stages and the one call"): the style and its sources as files
    in ``out_dir``. ``style.json`` names each source's data by its file; there is one file for each source, ``<source>.geojson``
    (``format="geojson"``, for MapLibre and to read) or ``<source>.parquet`` (``format="geoparquet"``, smaller, for DuckDB and large
    areas); and ``road_table.parquet`` holds every field of each road, by its row. The roads' own file has their drawing values only
    (and the columns in ``keep``). ``kwargs``: the keywords of ``export_inline``. Returns {file name: size in bytes}.
    ``tile_geojson`` makes the vector tiles from these files. The Rust engine only."""
    from . import _engine
    return _engine.export_geojson(edges, out_dir, format=format, keep=keep, **kwargs)


def tile_geojson(src_dir, out, *, format: str = "pmtiles", keep=None, base_url: str = "") -> Path:
    """Stage 2 of the Rust engine: the vector tiles of ``export_geojson``'s files in ``src_dir`` (GeoJSON or GeoParquet, as its
    ``style.json`` names them); it needs neither the roads nor the look. ``format="pmtiles"`` writes ``out`` as one archive;
    ``"xyz"`` writes the folder ``out``: ``roads/{z}/{x}/{y}`` and ``style.json`` (the style with one vector source, at
    ``<base_url>/roads/{z}/{x}/{y}``). ``keep``: more columns in the road tiles. The tiles are the tiles of ``export_style``'s one
    call. Returns ``out``. The Rust engine only."""
    from . import _engine
    return _engine.tile_geojson(src_dir, out, format=format, keep=keep, base_url=base_url)


def export_style(edges, out_dir, *, base_url: str, format: str = "xyz", **kwargs) -> Path:
    """Write the roads as ``style.json`` + vector tiles + a sprite into ``out_dir``; return the path of ``style.json``.

    ``edges``: a GeoDataFrame, or the path of a duckOSM GeoParquet file (``duckosm export-gis --format geoparquet``: the
    edges with their data and their drawing positions, docs/design/style_export.md version 2). A GeoParquet file without
    the positions is an error that says how to save them. ``base_url``: the URL where ``out_dir`` will be served. Every URL
    in the style is absolute (MapLibre does not say how it resolves a relative one). ``format``: ``"xyz"`` (default) writes
    a ``tiles/{z}/{x}/{y}.pbf`` folder, which every app and any static server can use; ``"pmtiles"`` writes one
    ``roads.pmtiles`` for MapLibre pages that register the ``pmtiles://`` protocol. The style holds the roads only: the base
    map comes from the app. The road tiles keep every column of the edges, so a click shows the data. ``kwargs``: the
    keywords of ``render_edges`` (profile, palette, overlays, ...); ``view_3d`` defaults to ``True`` here, so the style has
    the bridge decks for an app's own tilt. ``tile_format``: ``"mlt"`` (default; MapLibre Tile; files
    ``.mlt``, the style's source has ``"encoding": "mlt"``, and a PMTiles archive has the MLT tile type: MapLibre GL JS 5.12 or later) or ``"mvt"`` (files ``.pbf``).
    """
    if format not in ("xyz", "pmtiles"):
        raise ValueError(f"format must be 'xyz' or 'pmtiles', got {format!r}")
    if kwargs.get("views"):
        raise ValueError("export_style: views= are page-only (the page applies the first view at load); leave them out")
    if kwargs.get("color_active", 0):
        raise ValueError("export_style: color_active= is page-only (the style has the first colour option); leave it out")
    if kwargs.get("basemap") is not None:
        raise ValueError("export_style: the style holds the roads only, the base map comes from the app; leave basemap= out")
    name = kwargs.get("name") or (Path(edges).stem if isinstance(edges, (str, Path)) else "roads")
    if isinstance(edges, (str, Path)):
        import geopandas as gpd
        edges = gpd.read_parquet(edges)
        missing = [c for c in ("casing_level", "fill_level", "casing_start", "casing_end") if c not in edges.columns]
        if missing or edges[["casing_level", "fill_level"]].isna().any().any():
            raise ValueError("export_style: the GeoParquet file has no drawing positions for every edge "
                             f"({'no columns ' + ', '.join(missing) if missing else 'empty values'}). Save them into the duckOSM file first: "
                             "rs.save_levels(con, rs.compute_levels(edges)), then export it again (duckosm export-gis --format geoparquet).")
        for k, c in _LEVEL_COLS.items():
            if c in edges.columns:
                kwargs.setdefault(k, c)
    kwargs.setdefault("view_3d", True)        # the bridge decks: the page has a 3D button, an app has only its own tilt
    from . import _engine
    return _engine.export_style(edges, out_dir, base_url=base_url, format=format, **{**kwargs, "name": name})


def export_inline(edges, **kwargs) -> dict:
    """The style of ``export_style`` with the data inside (GeoJSON sources, no tiles, no files), for a plugin that makes the map in
    the browser (the roadstyle GeoLibre plugin runs roadstyle in Pyodide). The arrow icon is in the metadata (roadstyle:images), the
    page's popup, tooltip and hover settings in roadstyle:interaction. ``kwargs``: the keywords of ``render_edges``."""
    from . import _engine
    return _engine.export_inline(edges, **kwargs)


def _plugin_css():
    """static/popup.css for the plugin: each rule only under .rs-plugin, so an app's own popups keep their look."""
    css = re.sub(r"/\*.*?\*/", "", _assets.text("static/popup.css"), flags=re.S)
    css = re.sub(r"(^|})\s*([^{}]+?)\s*{", lambda m: m.group(1) + "\n" + ",".join(".rs-plugin " + x.strip() for x in m.group(2).split(",")) + "{", css)
    return css.strip() + "\n"


def export_look(path=None, *, profile=None, palette=None, edges=None, highway_col: str = "highway", oneway_col: str = "oneway",
                tunnel_col: str = "tunnel", bridge_col: str = "bridge", id_col: str = "edge_id", positions=None) -> dict:
    """The simple look for a data layer that another app draws (approach 2 of docs/design/style_export.md): MapLibre layers with no
    source, made from the profile and the palette, that read the raw duckOSM columns: the class colours and widths, a casing, the
    drawing order from ``casing_level`` / ``fill_level`` (one casing and one fill layer per position, in order), tunnels faded with a
    dashed casing, bridges with their casing, the two directions of a two-way road side by side. The GeoLibre plugin puts them on a
    GeoLibre data layer's source. Not in it (they need the full export): casing pieces at the ends, names, arrows, 3D decks.

    ``positions``: the drawing positions to make layers for; else those of ``edges`` (a GeoDataFrame or a GeoParquet path), else -10
    to 10. ``boundary`` in the result is the look of the area's outline (duckOSM's boundary file). Writes the JSON to ``path``
    if given; returns it."""
    from . import _engine
    if positions is None and edges is not None:
        import geopandas as gpd
        g = gpd.read_parquet(edges) if isinstance(edges, (str, Path)) else edges
        lv = [int(v) for c in ("casing_level", "fill_level") if c in g.columns for v in g[c].dropna().unique()]
        positions = range(min(lv, default=0), max(lv, default=0) + 1)
    lk = _engine._look_of({"palette": palette, "profile": profile})
    look = json.loads(_engine.rust().export_look(lk, [highway_col, oneway_col, tunnel_col, bridge_col, id_col],
                                                 [int(p) for p in (positions if positions is not None else range(-10, 11))]))
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(look, separators=(",", ":")))
    return look
