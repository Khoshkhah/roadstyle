"""Render styled edges with lonboard (deck.gl / WebGL) — fast for large edge sets.

Two PathLayers (casing under, fill over) mirror the folium "geometry sandwich".
"""
from __future__ import annotations

from .config import DEFAULT as CONFIG
from .style import resolve


def _hex_to_rgb(h, alpha=255):
    h = (h or "#000000").lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha]


def _arrays(gdf, palette, highway_col, tunnel_col, bridge_col, which):
    import numpy as np

    colors, widths = [], []
    for _, row in gdf.iterrows():
        rs = resolve(
            row.get(highway_col), palette=palette,
            tunnel=_truthy(row.get(tunnel_col)) if tunnel_col else False,
            bridge=_truthy(row.get(bridge_col)) if bridge_col else False,
        )
        if which == "casing":
            if rs.casing is None or rs.casing_width <= 0:
                colors.append([0, 0, 0, 0])       # invisible
                widths.append(0.0)
            else:
                colors.append(_hex_to_rgb(rs.casing, int(255 * rs.casing_opacity)))
                widths.append(rs.casing_width)
        else:
            colors.append(_hex_to_rgb(rs.fill, int(255 * rs.opacity)))
            widths.append(rs.width)
    return np.array(colors, dtype="uint8"), np.array(widths, dtype="float32")


def _truthy(v) -> bool:
    return str(v).strip().lower() in {"yes", "true", "1"} if v is not None else False


def _arrays_from_frame(rf, which):
    """Build (colors, widths) numpy arrays from a ResolvedFrame (the data-driven path)."""
    import numpy as np

    colors, widths = [], []
    n = len(rf)
    for i in range(n):
        if which == "casing":
            casing = rf.casing[i]
            if not casing or rf.casing_width[i] <= 0:
                colors.append([0, 0, 0, 0])
                widths.append(0.0)
            else:
                colors.append(_hex_to_rgb(casing, int(255 * rf.casing_opacity[i])))
                widths.append(rf.casing_width[i])
        else:
            colors.append(_hex_to_rgb(rf.fill[i], int(255 * rf.opacity[i])))
            widths.append(rf.width[i])
    return np.array(colors, dtype="uint8"), np.array(widths, dtype="float32")


def render(
    gdf,
    palette: str = "highsat",
    highway_col: str = "highway",
    tunnel_col: str | None = "tunnel",
    bridge_col: str | None = "bridge",
    basemap: str | None = None,
    styler=None,
    legend: bool = True,            # accepted for API parity; lonboard legend not yet supported
    legend_position: str = "bottomleft",
    **kwargs,
):
    from lonboard import Map, PathLayer

    from .basemaps import get_basemap

    # Arrows / labels / filter panel / base-layer switcher are web-backend UI; drop the kwargs so
    # they never reach lonboard.Map.
    for _k in ("arrows", "labels", "filter_control", "basemap_switcher"):
        kwargs.pop(_k, None)

    bm = get_basemap(basemap or CONFIG.basemap)
    carto_style = None
    try:
        from lonboard.basemap import CartoBasemap
        carto_style = getattr(CartoBasemap, bm.lonboard, None) if bm.lonboard else None
        if carto_style is None:   # osm/satellite have no Carto basemap -> sensible default
            carto_style = CartoBasemap.DarkMatter if bm.is_dark else CartoBasemap.Positron
    except Exception:
        carto_style = None

    g = gdf.to_crs(4326)

    if styler is None:
        tunnel_col = tunnel_col if (tunnel_col and tunnel_col in g.columns) else None
        bridge_col = bridge_col if (bridge_col and bridge_col in g.columns) else None
        c_col, c_w = _arrays(g, palette, highway_col, tunnel_col, bridge_col, "casing")
        f_col, f_w = _arrays(g, palette, highway_col, tunnel_col, bridge_col, "fill")
    else:
        rf = styler.resolve_frame(g)
        c_col, c_w = _arrays_from_frame(rf, "casing")
        f_col, f_w = _arrays_from_frame(rf, "fill")

    casing = PathLayer.from_geopandas(g, get_color=c_col, get_width=c_w,
                                      width_units="pixels", width_min_pixels=0)
    fill = PathLayer.from_geopandas(g, get_color=f_col, get_width=f_w,
                                    width_units="pixels", width_min_pixels=1)
    map_kw = dict(layers=[casing, fill])
    if carto_style is not None:
        map_kw["basemap_style"] = carto_style
    map_kw.update(kwargs)
    return Map(**map_kw)
