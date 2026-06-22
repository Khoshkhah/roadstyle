"""Top-level ``render_edges`` — normalise input, filter, then render with the chosen backend."""
from __future__ import annotations

from .edges import as_edges
from .filters import filter_edges
from .stylers import build_styler
from .validate import validate_edges


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
    **kwargs,
):
    """Render styled road edges on a map.

    Parameters
    ----------
    gdf : a :class:`roadstyle.RoadEdges` **or** a GeoDataFrame with a ``highway`` column
        (any CRS; normalised to EPSG:4326 line geometry for display). A plain GeoDataFrame is
        coerced to ``RoadEdges`` for you.
    backend : ``"folium"`` (portable HTML) or ``"lonboard"`` (WebGL).
    palette : ``"highsat"`` (high-saturation) or ``"carto"`` (OSM Carto).
    theme   : ``"light"`` | ``"dark"`` | ``"satellite"``.
    include / exclude : highway types to keep / drop (str or iterable) — see filter_edges.

    Data-driven styling (optional — when omitted, the classic OSM class styling is unchanged):
      - ``color_by`` : a column to colour by instead of road class.
      - ``colors``   : with ``color_by`` → categorical ``{value: hex}`` map.
      - ``cmap`` / ``vmin`` / ``vmax`` : with a numeric ``color_by`` → continuous colour ramp.
      - ``width_by`` : ``(min_px, max_px)`` to scale width with the numeric value.
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
    data_driven = style is not None or color_by is not None
    if data_driven:
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
