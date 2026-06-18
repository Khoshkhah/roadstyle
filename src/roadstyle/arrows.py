"""Direction arrows — a small chevron (">") at each edge's midpoint, pointing along the
geometry's source->target order.

Backend-agnostic geometry only; the folium backend wires the result onto the map (optionally
zoom-gated). Reached via ``render_edges(..., arrows=True)``. Drawing chevrons as plain line
geometry (one short 3-point polyline per edge) keeps them cheap — unlike per-edge text-path
overlays, which do not scale to thousands of edges.
"""
from __future__ import annotations

import math

_M_PER_DEG_LAT = 111_320.0


def chevron_features(gdf, where_col: str | None = None, size_m: float = 7.0):
    """A GeoJSON ``FeatureCollection`` of direction chevrons, one per edge.

    Each chevron is a 3-point ">" whose vertex sits at the edge midpoint and points in the
    geometry's source->target direction.

    Parameters
    ----------
    gdf : GeoDataFrame in EPSG:4326 with LineString geometry.
    where_col : optional column name; if given, only edges where that column is truthy get an
        arrow (e.g. a ``oneway`` flag). Missing column => all edges are arrowed.
    size_m : chevron barb length in metres (a fixed geographic size, so arrows scale with zoom).

    Non-LineString or zero-length geometries are skipped.
    """
    size_deg = size_m / _M_PER_DEG_LAT
    geoms = gdf.geometry.values
    mask = gdf[where_col].values if (where_col and where_col in gdf.columns) else None

    def _rot(vx, vy, deg):
        r = math.radians(deg)
        c, s = math.cos(r), math.sin(r)
        return vx * c - vy * s, vx * s + vy * c

    feats = []
    for i, geom in enumerate(geoms):
        if mask is not None and not bool(mask[i]):
            continue
        if geom is None or geom.geom_type != "LineString" or geom.length == 0:
            continue
        mid = geom.interpolate(0.5, normalized=True)
        a = geom.interpolate(0.49, normalized=True)
        b = geom.interpolate(0.51, normalized=True)
        cs = math.cos(math.radians(mid.y)) or 1e-6        # equal-aspect latitude correction
        dx, dy = (b.x - a.x) * cs, (b.y - a.y)
        dn = math.hypot(dx, dy)
        if dn == 0:
            continue
        ux, uy = dx / dn, dy / dn                          # unit travel direction (corrected frame)
        tx, ty = mid.x * cs, mid.y                         # tip at the midpoint
        (b1x, b1y), (b2x, b2y) = _rot(-ux, -uy, 35), _rot(-ux, -uy, -35)   # barbs trailing the tip
        to_ll = lambda px, py: [px / cs, py]               # back to lon/lat
        feats.append({"type": "Feature", "properties": {}, "geometry": {"type": "LineString",
            "coordinates": [to_ll(tx + b1x * size_deg, ty + b1y * size_deg),
                            to_ll(tx, ty),
                            to_ll(tx + b2x * size_deg, ty + b2y * size_deg)]}})
    return {"type": "FeatureCollection", "features": feats}
