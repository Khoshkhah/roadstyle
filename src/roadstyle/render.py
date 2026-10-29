"""Top-level ``render_edges`` — normalise input, filter, then render with the chosen backend."""
from __future__ import annotations

import json
import warnings
from collections.abc import Mapping

from .edges import as_edges


def _color_map(table, key_col: str, color_col: str) -> dict:
    """Normalise an ``edge_id -> colour`` table to ``{str(id): colour}``. Accepts a dict / mapping,
    a pandas Series (index = id), or a DataFrame with ``key_col`` + ``color_col`` columns."""
    if isinstance(table, Mapping):
        return {str(k): v for k, v in table.items()}
    if hasattr(table, "to_dict") and not hasattr(table, "columns"):   # a pandas Series
        return {str(k): v for k, v in table.to_dict().items()}
    try:                                                              # a DataFrame-like
        return {str(k): v for k, v in zip(table[key_col], table[color_col], strict=False)}
    except Exception as e:
        raise ValueError(
            f"color_table must be a dict, a Series, or a DataFrame with {key_col!r} and "
            f"{color_col!r} columns") from e


def _named_basemaps(kwargs, api_key):
    """A base map given as an object (a ``Basemap``, an xyzservices ``TileProvider``) is registered under its key, and the call names it
    by that key: the page's base maps are names."""
    from .basemaps import get_basemap, register_basemap

    def named(b):
        if b is None or isinstance(b, str):
            return b
        bm = get_basemap(b, api_key=api_key)
        register_basemap(bm)
        return bm.key
    out = dict(kwargs)
    if "basemap" in out:
        out["basemap"] = named(out["basemap"])
    if out.get("basemaps") is not None:
        out["basemaps"] = [named(b) for b in out["basemaps"]]
    return out


def _warn_unclassed(g, col):
    """Warn once when edges have no class (None, NaN or ""): they are drawn with the default style."""
    if col not in g.columns:
        return
    bad = g[g[col].isna() | (g[col].astype(str).str.strip() == "")]
    if bad.empty:
        return
    idc = next((c for c in ("edge_ref", "edge_id", "osm_edge_id", "id") if c in g.columns), None)
    names = [str(v) for v in (bad[idc] if idc else bad.index)[:5]]
    warnings.warn(f"{len(bad)} edges have no '{col}' value: they are drawn with the default style; usually bad data, e.g. an area outline "
                  f"(area:highway) taken as a road ({idc or 'row'}: {', '.join(names)}{' ...' if len(bad) > 5 else ''})", stacklevel=3)


def _check_keywords(kwargs):
    """render_edges takes **kwargs. A keyword that no part of roadstyle reads (roadstyle::options::unknown) is an error, with the nearest
    known one. The names that start with "_" are internal hooks."""
    from ._engine import rust
    names = [k for k in kwargs if not k.startswith("_")]
    bad = [f"{k!r}" + (f" (did you mean {near!r}?)" if near else "") for k, near in rust().unknown_keywords(names)]
    if bad:
        raise ValueError(f"render_edges: unknown keyword {', '.join(bad)}")


def render_edges(
    gdf,
    *,
    backend: str = "web",
    palette: str = "amber",
    highway_col: str = "highway",
    include=None,
    exclude=None,
    match_links: bool = True,
    # data-driven styling (all None => classic OSM class styling, unchanged path)
    style=None,
    color_by: str | None = None,
    colors=None,
    cmap=None,
    vmin: float | None = None,
    vmax: float | None = None,
    width_by=None,
    # per-edge colour table (edge_id -> colour); edges not in it get a gray fallback
    color_table=None,
    color_key: str = "edge_id",
    color_col: str = "color",
    settings=None,
    profile: str | None = None,
    api_key: str | None = None,
    levels_db=None,
    **kwargs,
):
    """Render styled road edges on a map.

    Parameters
    ----------
    gdf : a :class:`roadstyle.RoadEdges` **or** a GeoDataFrame with a ``highway`` column
        (any CRS; normalised to EPSG:4326 line geometry for display). A plain GeoDataFrame is
        coerced to ``RoadEdges`` for you.
    backend : ``"web"`` (self-contained MapLibre, default), ``"folium"`` (portable HTML), or
        ``"lonboard"`` (WebGL).
    palette : ``"amber"`` (the default), ``"carto"`` (OSM Carto), ``"highsat"`` (high-saturation) or ``"mono"``.
    profile : the name of a profile: every style value that is not a color (widths, zooms, sizes, dashes). ``None``: the one in
        force (``default``, or what the settings name). Bundled: ``default``, ``highsat``; own ones in ``./profiles/<name>.yaml``
        (docs/design/style_config.md). ``palette`` names the colors the same way (bundled and ``./palettes/<name>.yaml``).
    include / exclude : highway types to keep / drop (str or iterable) — see filter_edges.

    Data-driven styling (optional — when omitted, the classic OSM class styling is unchanged):
      - ``color_by`` : a column to colour by instead of road class.
      - ``colors``   : with ``color_by`` → categorical ``{value: hex}`` map, or ``"self"`` to use the
        column's own value as the literal colour (gray fallback for blank/invalid).
      - ``cmap`` / ``vmin`` / ``vmax`` : with a numeric ``color_by`` → continuous colour ramp.
      - ``width_by`` : ``(min_px, max_px)`` to scale width with the numeric value.
      - ``color_table`` : a per-edge colour map keyed by ``color_key`` (default ``"edge_id"``) — a
        dict ``{id: colour}``, a Series, or a DataFrame with ``color_key`` + ``color_col`` (default
        ``"color"``). Edges not in the table get a **gray** fallback. Keeps class widths + casing,
        so roads still read as roads; works on every backend.
      - ``style``    : pass a built :class:`roadstyle.Styler` directly (overrides the above).

    Extra kwargs pass through to the backend renderer, e.g.:
      - ``basemap`` : override the primary base map setting (a key in ``roadstyle.BASEMAPS``).
      - ``basemaps``: a list of base-map keys offered as toggleable layers / a switcher.
      - ``selected`` / ``name`` : edges to highlight / the map title.
      - ``tooltip`` : hover fields (list of columns), on every backend. On **web** it aliases
        ``road_tooltip`` (the web-native name); ``road_popup`` is the separate click popup.
      - ``arrows`` / ``labels`` / ``filter_control`` / ``basemap_switcher`` : (web backend) toggle
        the one-way arrows, street-name labels, road-class filter panel, and base-layer dropdown.
      - ``filter_col`` : (web backend) column the filter panel lists/filters by, when it should
        differ from the styling ``highway_col`` — e.g. width/casing follow an OSM-highway proxy
        while the filter lists the source's own road class. Default ``None`` = filter by ``highway_col``.
      - ``levels_db`` : (web backend) a duckOSM file: the stored drawing order (``visualization.edge_levels``, ``duckosm levels``) is read for these edges, which may be
        some of the edges it was solved for (one mode of the file); ids ``int64`` or text (``edge_id_col``). Not with level columns of your own. A ``ValueError`` says what is
        missing: no stored levels, or an edge without a row.
      - ``boundary`` : (web backend) a shapely geometry / GeoDataFrame / GeoJSON mapping drawn as a
        dashed outline on top of the roads (e.g. the area the network was clipped to).
    """
    if "order_col" in kwargs:
        raise ValueError("order_col is removed: roadstyle draws by positions (docs/design/levels_split_casing.md, section 12)")
    for k in ("band_col", "order"):     # inputs of the level step, not of the drawing (docs/design/level_input.md), for both engines
        if k in kwargs:
            raise ValueError(f"render_edges takes no {k}: compute the levels first (rs.compute_levels(edges, {k}=...), or rs.level_input + "
                             "rs.solve_levels) and pass casing_level_col / fill_level_col / casing_start_col / casing_end_col")
    if kwargs.get("template") is not None:      # render_dashboard, render_report: the template's keywords where the call gives none
        from . import _engine
        for k, v in json.loads(_engine.rust().template_keys()).get(kwargs["template"], {}).items():
            kwargs.setdefault(k, v)
    for k, why in (("engine", "roadstyle has one engine, the Rust engine"), ("simple", "the simple look is the only look")):
        if k in kwargs:
            raise ValueError(f"{k}= is removed: {why} (CHANGELOG, 0.26.0)")
    if backend == "web":
        _check_keywords(kwargs)
    if backend == "web":
        from . import _engine
        if style is not None:
            raise ValueError("a Styler object (style=) is not in the web page: use color_by, colors, cmap, vmin, vmax or width_by")
        _warn_unclassed(as_edges(gdf, class_col=highway_col).gdf, highway_col)
        kwargs = _named_basemaps(kwargs, api_key)
        data = {k: v for k, v in (("color_by", color_by), ("colors", colors), ("cmap", cmap), ("vmin", vmin), ("vmax", vmax),
                                  ("width_by", width_by), ("color_table", color_table)) if v is not None}
        if color_table is not None:         # a mapping, a Series or a DataFrame: {edge id as text: colour}
            data["color_table"] = _color_map(color_table, color_key, color_col)
        return _engine.render_page(gdf, palette=palette, profile=profile, settings=settings, highway_col=highway_col, include=include,
                                   exclude=exclude, match_links=match_links, levels_db=levels_db, api_key=api_key, **data, **kwargs)
    raise ValueError(f"unknown backend {backend!r}: the only backend is 'web' (the folium and lonboard backends are removed)")
