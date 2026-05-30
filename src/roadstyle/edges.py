"""The canonical road-edge input: :class:`RoadEdges` + its converters.

roadstyle's *one* internal input shape ("the special format") is a set of road edges normalised
to: **EPSG:4326**, **line geometry** (LineString/MultiLineString), a **class column** (default
``highway``) and any number of extra data columns (``aadt``, ``congestion``, …). :class:`RoadEdges`
guarantees that shape; the converters bring arbitrary sources into it:

- :func:`normalize_edges` — an in-memory GeoDataFrame → ``RoadEdges`` (reproject, drop non-lines,
  optional column rename);
- :func:`load_edges` / :meth:`RoadEdges.from_file` — load *any* geo file (GeoPackage, GeoJSON,
  Shapefile, …) straight to ``RoadEdges``.

It stays a thin wrapper around a normalised GeoDataFrame (always available as ``.gdf``), so it does
not fight the geopandas ecosystem — and :func:`roadstyle.render_edges` accepts either a ``RoadEdges``
or a plain GeoDataFrame.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

from .validate import to_wgs84, validate_edges

_LINE = {"LineString", "MultiLineString"}


@dataclass
class RoadEdges:
    """A normalised set of road edges (EPSG:4326, line geometry) + which column is the class.

    Build it with :meth:`from_geodataframe` / :meth:`from_file` (or :func:`normalize_edges` /
    :func:`load_edges`), not the bare constructor, so the canonical guarantees hold.
    """
    gdf: object                 # a normalised GeoDataFrame (EPSG:4326, line geometry)
    class_col: str = "highway"  # the default class column for class-based styling

    def __len__(self) -> int:
        return len(self.gdf)

    @property
    def columns(self) -> list[str]:
        return list(self.gdf.columns)

    def to_geodataframe(self):
        """Return the underlying normalised GeoDataFrame."""
        return self.gdf

    @classmethod
    def from_geodataframe(
        cls, gdf, *, class_col: str = "highway", rename=None, keep_non_lines: bool = False
    ) -> "RoadEdges":
        """Normalise an in-memory GeoDataFrame into canonical :class:`RoadEdges`.

        Steps: validate → optional ``rename`` of columns → drop non-line geometry (unless
        ``keep_non_lines``) → reproject to EPSG:4326 (skipped if already 4326).
        """
        if isinstance(gdf, cls):
            return gdf
        validate_edges(gdf)                       # type / non-empty / has geometry
        g = gdf.rename(columns=dict(rename)) if rename else gdf

        if not keep_non_lines:
            mask = g.geom_type.isin(_LINE)
            dropped = int((~mask).sum())
            if dropped:
                warnings.warn(
                    f"RoadEdges dropped {dropped} non-line "
                    f"geometr{'y' if dropped == 1 else 'ies'} "
                    "(roadstyle styles road edges; lines only).",
                    stacklevel=2,
                )
                g = g[mask]

        g = to_wgs84(g)                           # canonical CRS for web display
        return cls(g, class_col=class_col)

    @classmethod
    def from_file(
        cls, path, *, class_col: str = "highway", layer=None, rename=None
    ) -> "RoadEdges":
        """Load a geo file (GeoPackage/GeoJSON/Shapefile/…) into canonical :class:`RoadEdges`."""
        import geopandas as gpd

        gdf = gpd.read_file(path, layer=layer) if layer is not None else gpd.read_file(path)
        return cls.from_geodataframe(gdf, class_col=class_col, rename=rename)


def normalize_edges(gdf, *, class_col: str = "highway", rename=None) -> RoadEdges:
    """Convert an in-memory GeoDataFrame into canonical :class:`RoadEdges`."""
    return RoadEdges.from_geodataframe(gdf, class_col=class_col, rename=rename)


def load_edges(path, *, class_col: str = "highway", layer=None, rename=None) -> RoadEdges:
    """Load any geo file into canonical :class:`RoadEdges` (geopandas-backed)."""
    return RoadEdges.from_file(path, class_col=class_col, layer=layer, rename=rename)


def as_edges(data, *, class_col: str = "highway") -> RoadEdges:
    """Coerce a :class:`RoadEdges` *or* a plain GeoDataFrame into a ``RoadEdges``."""
    if isinstance(data, RoadEdges):
        return data
    return RoadEdges.from_geodataframe(data, class_col=class_col)
