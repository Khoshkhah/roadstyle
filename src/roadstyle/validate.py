"""Input validation + CRS handling, with clear, early error messages.

The goal is to fail *loudly and helpfully* before rendering: a missing column should say
which columns *are* present, not raise a cryptic ``KeyError`` deep inside pandas.
"""
from __future__ import annotations

import warnings

#: geometry types roadstyle knows how to draw (road edges are lines)
_LINE_TYPES = {"LineString", "MultiLineString"}


def validate_edges(gdf, column: str | None = None, *, name: str = "gdf"):
    """Validate a road-edge GeoDataFrame; return it unchanged if OK.

    Raises a clear ``TypeError``/``ValueError`` for the common mistakes (wrong type, empty,
    no geometry, missing styling column) and *warns* on non-line geometries.
    """
    import geopandas as gpd

    if not isinstance(gdf, gpd.GeoDataFrame):
        raise TypeError(f"{name} must be a GeoDataFrame, got {type(gdf).__name__}")
    if len(gdf) == 0:
        raise ValueError(f"{name} is empty — there are no edges to render")
    if gdf.geometry is None or bool(gdf.geometry.isna().all()):
        raise ValueError(f"{name} has no geometry")
    if column is not None and column not in gdf.columns:
        cols = ", ".join(map(str, gdf.columns)) or "(none)"
        raise ValueError(
            f"styling column {column!r} not found in {name}; available columns: {cols}"
        )

    geom_types = set(gdf.geom_type.dropna().unique())
    if geom_types and not geom_types <= _LINE_TYPES:
        bad = sorted(geom_types - _LINE_TYPES)
        warnings.warn(
            f"{name} contains non-line geometries {bad}; roadstyle styles road edges "
            "(LineString/MultiLineString) and may render these oddly.",
            stacklevel=2,
        )
    return gdf


def to_wgs84(gdf, *, name: str = "gdf"):
    """Return ``gdf`` in EPSG:4326 (web display CRS), reprojecting only if needed.

    Skips the reprojection when the data is already in 4326 (cheaper, lossless), and raises
    a clear error when the CRS is unknown instead of letting ``to_crs`` fail cryptically.
    """
    if gdf.crs is None:
        raise ValueError(
            f"{name} has no CRS set, so it cannot be reprojected to EPSG:4326 for web "
            "display. Set it first, e.g. gdf.set_crs(epsg=3006) if you know the source CRS."
        )
    try:
        epsg = gdf.crs.to_epsg()
    except Exception:
        epsg = None
    if epsg == 4326:
        return gdf
    return gdf.to_crs(4326)
