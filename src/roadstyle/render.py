"""Top-level ``render_edges`` — normalise input, filter, then render with the chosen backend."""
from __future__ import annotations

import warnings
from collections.abc import Mapping

from .edges import as_edges
from .filters import filter_edges
from .palettes import DEFAULT_PALETTE
from .stylers import build_styler
from .validate import validate_edges


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


def render_edges(
    gdf,
    *,
    backend: str = "web",
    palette: str = DEFAULT_PALETTE,
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
    engine: str | None = None,
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
    if kwargs.get("sidebar") is not None:      # render_dashboard, render_report: the sidebar's keywords where the call gives none
        from .pages import SIDEBAR_DEFAULTS
        for k, v in SIDEBAR_DEFAULTS.get(kwargs["sidebar"], {}).items():
            kwargs.setdefault(k, v)
    from . import _engine
    hooks = [k for k in ("_export", "_parts", "_edges", "_palette_copy") if kwargs.get(k) is not None and kwargs.get(k) is not False]
    # ``engine``: "python" (default) or "rust" (the roads' style from the Rust engine, the page from Python). The internal hooks of the
    # export and the level editor are Python's; folium and lonboard are other renderers, for which the engine does not apply
    rust_page = _engine.engine(engine) == "rust" and not hooks and backend == "web"
    if engine == "rust" and backend != "web":
        raise ValueError(f"engine='rust' makes the web page only, not backend={backend!r}")
    if rust_page:
        why = (["a Styler object (style=)"] if style is not None else []) + (["simple=False (the full look)"] if kwargs.get("simple") is False else [])
        if why and _engine.fallback(engine, ", ".join(why) + " is Python's"):
            rust_page = False
    if kwargs.get("live_data") and not rust_page:
        raise ValueError("live_data=True needs the Rust engine's web page (engine='rust', backend='web', no style= and no simple=False)")
    if rust_page:
        _warn_unclassed(as_edges(gdf, class_col=highway_col).gdf, highway_col)
        data = {k: v for k, v in (("style", style), ("color_by", color_by), ("colors", colors), ("cmap", cmap), ("vmin", vmin), ("vmax", vmax),
                                  ("width_by", width_by), ("color_table", color_table)) if v is not None}
        if color_table is not None:         # a mapping, a Series or a DataFrame: {edge id as text: colour}, as the Python path reads it
            data["color_table"] = _color_map(color_table, color_key, color_col)
        return _engine.render_page(gdf, palette=palette, profile=profile, settings=settings, highway_col=highway_col, include=include,
                                   exclude=exclude, match_links=match_links, levels_db=levels_db, api_key=api_key, engine=engine, **data, **kwargs)
    from . import _settings as _st
    pick = {k: v for k, v in (("profile", profile), ("palette", palette)) if v is not None and v != _st.theme()["active"][k]
            and (k == "profile" or v in _st.style_names("palettes"))}      # a palette made in code (register_palette) has no file
    if pick:
        # a profile / palette by name for THIS render (docs/design/style_config.md): a settings source after any settings= of the call
        settings = [settings, pick] if settings is not None else pick
        profile = None
    if settings is not None:
        # scoped settings: apply the override for THIS render only, then restore. Same layout as
        # a roadstyle.json / use_settings source (dict or path); stacks on top of any overrides
        # already active.
        from . import _settings as _s
        from . import use_settings as _use
        call_args = {k: v for k, v in locals().items()
                     if k not in ("gdf", "settings", "kwargs", "_s", "_use", "_st", "pick")}
        prev = list(_s._EXTRA)
        try:
            _use(*prev, *(settings if isinstance(settings, list) else [settings]))
            return render_edges(gdf, settings=None, **call_args, **kwargs)
        finally:
            _use(*prev)

    edges = as_edges(gdf, class_col=highway_col)   # canonical: RoadEdges (EPSG:4326, lines)
    g = edges.gdf
    col = edges.class_col

    _warn_unclassed(g, col)

    # Decide styling. No data-driven args => classic OSM path (validate the class column).
    if color_table is not None:
        # per-edge colour from an edge_id -> colour map; keep class widths/casing, gray fallback
        from .stylers import ColorTableStyler
        if color_key not in g.columns:
            raise ValueError(
                f"color_key {color_key!r} not found in the edges (columns: {list(g.columns)})")
        mapping = _color_map(color_table, color_key, color_col)
        g = g.copy()
        g["__rs_color"] = [mapping.get(str(k)) for k in g[color_key]]
        styler = ColorTableStyler(color_column="__rs_color", highway_col=col, palette=palette)
    elif style is not None or color_by is not None:
        validate_edges(g, color_by or col)
        styler = build_styler(
            style=style, palette=palette, highway_col=col,
            color_by=color_by, colors=colors, cmap=cmap,
            vmin=vmin, vmax=vmax, width_by=width_by,
        )
    else:
        validate_edges(g, col)                      # clear error if the class column is missing
        styler = None

    if include is not None or exclude is not None:
        g = filter_edges(g, include=include, exclude=exclude,
                         highway_col=col, match_links=match_links)
    if levels_db is not None:
        if backend != "web":
            raise ValueError("levels_db is for the web backend")
        if any(kwargs.get(k) for k in ("casing_level_col", "fill_level_col", "casing_start_col", "casing_end_col")):
            raise ValueError("levels_db and level columns of your own (casing_level_col, fill_level_col, ...) are two drawing orders: use one")
        from .levels_store import stored_levels
        g, level_kw = stored_levels(levels_db, g, kwargs.get("edge_id_col", "edge_id"))
        kwargs = {**kwargs, **level_kw}
    if backend == "folium":
        from .render_folium import render
    elif backend == "lonboard":
        from .render_lonboard import render
    elif backend == "web":
        from .render_web import render
    else:
        raise ValueError(f"unknown backend {backend!r}; use 'folium', 'lonboard', or 'web'")
    return render(g, palette=palette, highway_col=col, styler=styler, api_key=api_key, **kwargs)
