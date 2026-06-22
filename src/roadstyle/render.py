"""Top-level ``render_edges`` — normalise input, filter, then render with the chosen backend."""
from __future__ import annotations

from collections.abc import Mapping

from .edges import as_edges
from .filters import filter_edges
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
        return {str(k): v for k, v in zip(table[key_col], table[color_col])}
    except Exception as e:
        raise ValueError(
            f"color_table must be a dict, a Series, or a DataFrame with {key_col!r} and "
            f"{color_col!r} columns") from e


def render_edges(
    gdf,
    *,
    backend: str = "web",
    palette: str = "highsat",
    theme: str = "dark",
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
    palette : ``"highsat"`` (high-saturation) or ``"carto"`` (OSM Carto).
    theme   : ``"light"`` | ``"dark"`` | ``"satellite"``.
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
      - ``basemap`` : override the theme's base map (a key in ``roadstyle.BASEMAPS``).
      - ``basemaps``: a list of base-map keys offered as toggleable layers / a switcher.
      - ``tooltip`` / ``selected`` / ``name``.
      - ``arrows`` / ``labels`` / ``filter_control`` / ``basemap_switcher`` : (web backend) toggle
        the one-way arrows, street-name labels, road-class filter panel, and base-layer dropdown.
    """
    edges = as_edges(gdf, class_col=highway_col)   # canonical: RoadEdges (EPSG:4326, lines)
    g = edges.gdf
    col = edges.class_col

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
    if backend == "folium":
        from .render_folium import render
    elif backend == "lonboard":
        from .render_lonboard import render
    elif backend == "web":
        from .render_web import render
    else:
        raise ValueError(f"unknown backend {backend!r}; use 'folium', 'lonboard', or 'web'")
    return render(g, palette=palette, theme=theme, highway_col=col, styler=styler, **kwargs)
