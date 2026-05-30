"""Top-level ``render_edges`` — normalise input, filter, then render with the chosen backend."""
from __future__ import annotations

from .edges import as_edges
from .filters import filter_edges
from .validate import validate_edges


def render_edges(
    gdf,
    *,
    backend: str = "folium",
    palette: str = "highsat",
    theme: str = "dark",
    highway_col: str = "highway",
    include=None,
    exclude=None,
    match_links: bool = True,
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
    Extra kwargs pass through to the backend renderer, e.g.:
      - ``basemap`` : override the theme's base map (a key in ``roadstyle.BASEMAPS``).
      - ``basemaps``: (folium) a list of base-map keys offered as toggleable radio layers.
      - ``tooltip`` / ``selected`` / ``name``.
    """
    edges = as_edges(gdf, class_col=highway_col)   # canonical: RoadEdges (EPSG:4326, lines)
    g = edges.gdf
    col = edges.class_col
    validate_edges(g, col)                          # clear error if the class column is missing

    if include is not None or exclude is not None:
        g = filter_edges(g, include=include, exclude=exclude,
                         highway_col=col, match_links=match_links)
    if backend == "folium":
        from .render_folium import render
    elif backend == "lonboard":
        from .render_lonboard import render
    else:
        raise ValueError(f"unknown backend {backend!r}; use 'folium' or 'lonboard'")
    return render(g, palette=palette, theme=theme, highway_col=col, **kwargs)
