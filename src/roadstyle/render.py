"""Top-level ``render_edges`` — filter, then render with the chosen backend."""
from __future__ import annotations

from .filters import filter_edges


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
    gdf : GeoDataFrame with a ``highway`` column (any CRS; reprojected to 4326 for display).
    backend : ``"folium"`` (portable HTML) or ``"lonboard"`` (WebGL).
    palette : ``"highsat"`` (high-saturation) or ``"carto"`` (OSM Carto).
    theme   : ``"light"`` | ``"dark"`` | ``"satellite"``.
    include / exclude : highway types to keep / drop (str or iterable) — see filter_edges.
    Extra kwargs pass through to the backend renderer, e.g.:
      - ``basemap`` : override the theme's base map (a key in ``roadstyle.BASEMAPS``).
      - ``basemaps``: (folium) a list of base-map keys offered as toggleable radio layers.
      - ``tooltip`` / ``selected`` / ``name``.
    """
    if include is not None or exclude is not None:
        gdf = filter_edges(gdf, include=include, exclude=exclude,
                           highway_col=highway_col, match_links=match_links)
    if backend == "folium":
        from .render_folium import render
    elif backend == "lonboard":
        from .render_lonboard import render
    else:
        raise ValueError(f"unknown backend {backend!r}; use 'folium' or 'lonboard'")
    return render(gdf, palette=palette, theme=theme, highway_col=highway_col, **kwargs)
