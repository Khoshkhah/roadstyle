"""The canonical road-edge input: :class:`RoadEdges` + its converters.

roadstyle's *one* internal input shape ("the special format") is a set of road edges normalised
to: **EPSG:4326**, **line geometry** (LineString/MultiLineString), a **class column** (default
``highway``) and any number of extra data columns (``aadt``, ``congestion``, …). :class:`RoadEdges`
guarantees that shape; the converters bring arbitrary sources into it.

Everything funnels through :func:`as_edges`, so every entry point (:func:`roadstyle.render_edges`,
:func:`roadstyle.to_spec`, …) accepts **any** of these without extra code:

- a :class:`RoadEdges` (passthrough) or a **GeoDataFrame** (:func:`normalize_edges`);
- a **file path** — GeoPackage / GeoJSON / Shapefile / … (:func:`load_edges`);
- a **GeoJSON mapping** — FeatureCollection / Feature / geometry, a roadstyle *spec* dict, or any
  object with ``__geo_interface__`` (:func:`from_geojson`);
- a **pyarrow Table** (:func:`from_arrow`);
- a **DuckDB** relation, or a connection + SQL query (:func:`from_duckdb`).

For control over geometry column / CRS (DuckDB, Arrow), call the matching ``from_*`` helper and pass
its result straight to ``render_edges``.
"""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass

from .validate import to_wgs84, validate_edges

_LINE = {"LineString", "MultiLineString"}
_GEOM_TYPES = {
    "Point", "MultiPoint", "LineString", "MultiLineString",
    "Polygon", "MultiPolygon", "GeometryCollection",
}
#: column names commonly holding geometry in DuckDB / Arrow / SQL results
_GEOM_CANDIDATES = ("geometry", "geom", "wkb_geometry", "geom_wkb", "the_geom", "wkt", "wkb")


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
    ) -> RoadEdges:
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
    ) -> RoadEdges:
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


# ── widened input boundary: GeoJSON / Arrow / DuckDB → GeoDataFrame → RoadEdges ────────────────

def _table_to_gdf(df, *, geometry=None, crs=None):
    """Turn a (pandas) DataFrame with a geometry column into a GeoDataFrame.

    The geometry column may hold WKB ``bytes``, WKT ``str``, or shapely geometries. ``geometry``
    names the column (else the first of :data:`_GEOM_CANDIDATES` that is present).
    """
    import geopandas as gpd
    from shapely.geometry.base import BaseGeometry

    if isinstance(df, gpd.GeoDataFrame):
        return df

    cols = list(df.columns)
    candidates = ([geometry] if geometry else []) + list(_GEOM_CANDIDATES)
    col = next((c for c in candidates if c and c in cols), None)
    if col is None:
        avail = ", ".join(map(str, cols)) or "(none)"
        raise ValueError(
            f"could not find a geometry column; pass geometry=<column name>. Available: {avail}"
        )

    s = df[col]
    nonnull = s.dropna()
    sample = nonnull.iloc[0] if len(nonnull) else None
    if isinstance(sample, (bytes, bytearray, memoryview)):
        # shapely.from_wkb wants bytes/str; DuckDB BLOBs arrive as bytearray/memoryview
        wkb = [bytes(v) if isinstance(v, (bytearray, memoryview)) else v for v in s]
        geom = gpd.GeoSeries.from_wkb(wkb, index=df.index, crs=crs)
    elif isinstance(sample, str):
        geom = gpd.GeoSeries.from_wkt(list(s), index=df.index, crs=crs)
    elif sample is None or isinstance(sample, BaseGeometry):
        geom = gpd.GeoSeries(list(s), index=df.index, crs=crs)
    else:
        raise ValueError(
            f"geometry column {col!r} holds {type(sample).__name__} values; expected WKB bytes, "
            "WKT strings, or shapely geometries (in DuckDB select ST_AsWKB(geom) / ST_AsText(geom))"
        )
    return gpd.GeoDataFrame(df.drop(columns=[col]), geometry=geom, crs=crs)


def _geojson_features(obj):
    """Extract a list of GeoJSON Feature mappings from the many shapes people pass."""
    if hasattr(obj, "__geo_interface__") and not isinstance(obj, dict):
        obj = obj.__geo_interface__
    if isinstance(obj, dict):
        if isinstance(obj.get("geojson"), dict):     # a roadstyle spec → its FeatureCollection
            obj = obj["geojson"]
        t = obj.get("type")
        if t == "FeatureCollection":
            return obj.get("features", [])
        if t == "Feature":
            return [obj]
        if t in _GEOM_TYPES:                          # a bare geometry
            return [{"type": "Feature", "geometry": obj, "properties": {}}]
        if "features" in obj:
            return obj["features"]
    if isinstance(obj, (list, tuple)):
        return list(obj)
    raise TypeError(
        "unsupported GeoJSON input; expected a FeatureCollection / Feature / geometry mapping, "
        "a roadstyle spec, a list of features, or an object with __geo_interface__"
    )


def from_geojson(obj, *, class_col: str = "highway", crs=4326, rename=None) -> RoadEdges:
    """Build canonical :class:`RoadEdges` from a GeoJSON mapping.

    Accepts a FeatureCollection / Feature / geometry mapping, a roadstyle ``to_spec`` dict, a list
    of features, or any object exposing ``__geo_interface__``. Plain GeoJSON has no CRS, so
    EPSG:4326 (the GeoJSON default) is assumed unless ``crs`` is given.
    """
    import geopandas as gpd

    gdf = gpd.GeoDataFrame.from_features(_geojson_features(obj), crs=crs)
    return RoadEdges.from_geodataframe(gdf, class_col=class_col, rename=rename)


def from_arrow(
    table, *, class_col: str = "highway", geometry=None, crs=None, rename=None
) -> RoadEdges:
    """Build canonical :class:`RoadEdges` from a **pyarrow Table**.

    Uses geopandas' native GeoArrow reader when available; otherwise falls back to a pandas
    conversion that decodes a WKB/WKT geometry column (``geometry``).
    """
    import geopandas as gpd

    gdf = None
    reader = getattr(gpd.GeoDataFrame, "from_arrow", None)
    if reader is not None:
        try:
            cand = reader(table)
            _ = cand.geometry                        # raises if no active geometry → fall back
            gdf = cand
        except Exception:                            # not GeoArrow-encoded → decode WKB/WKT
            gdf = None
    if gdf is None:
        gdf = _table_to_gdf(table.to_pandas(), geometry=geometry, crs=crs)
    if crs is not None and gdf.crs is None:
        gdf = gdf.set_crs(crs)
    return RoadEdges.from_geodataframe(gdf, class_col=class_col, rename=rename)


def from_duckdb(
    connection, query=None, *, geometry=None, class_col: str = "highway", crs=4326, rename=None
) -> RoadEdges:
    """Build canonical :class:`RoadEdges` from **DuckDB**.

    Pass either a relation (``con.sql("SELECT …")``) or a connection **plus** a ``query`` string.
    Select the geometry as WKB or WKT so it round-trips, e.g.::

        rs.from_duckdb(con, "SELECT highway, aadt, ST_AsWKB(geom) AS geom FROM roads",
                       geometry="geom", crs=3006)

    DuckDB doesn't carry a CRS, so ``crs`` (default EPSG:4326) says what the coordinates are in;
    reprojection to 4326 then happens automatically.
    """
    rel = connection
    if query is not None:
        if hasattr(connection, "sql"):
            rel = connection.sql(query)
        elif hasattr(connection, "execute"):
            rel = connection.execute(query)
        else:
            raise TypeError("from_duckdb: pass a DuckDB connection when giving a query string")

    for attr in ("df", "fetchdf", "to_df"):
        getter = getattr(rel, attr, None)
        if callable(getter):
            df = getter()
            break
    else:
        raise TypeError("from_duckdb: expected a DuckDB connection, relation, or result object")

    gdf = _table_to_gdf(df, geometry=geometry, crs=crs)
    return RoadEdges.from_geodataframe(gdf, class_col=class_col, rename=rename)


def as_edges(data, *, class_col: str = "highway") -> RoadEdges:
    """Coerce any supported input into canonical :class:`RoadEdges`.

    Accepts: :class:`RoadEdges` (passthrough) · GeoDataFrame · file path · GeoJSON mapping /
    ``__geo_interface__`` · pyarrow Table · DuckDB relation. For options (geometry column, CRS)
    call :func:`from_duckdb` / :func:`from_arrow` / :func:`from_geojson` / :func:`load_edges`.
    """
    if isinstance(data, RoadEdges):
        return data

    import geopandas as gpd

    if isinstance(data, gpd.GeoDataFrame):
        return RoadEdges.from_geodataframe(data, class_col=class_col)
    if isinstance(data, (str, os.PathLike)):
        return load_edges(data, class_col=class_col)

    top = type(data).__module__.split(".", 1)[0]
    if top == "duckdb":
        return from_duckdb(data, class_col=class_col)
    if top == "pyarrow":
        return from_arrow(data, class_col=class_col)
    if isinstance(data, dict) or hasattr(data, "__geo_interface__"):
        return from_geojson(data, class_col=class_col)

    raise TypeError(
        f"don't know how to read edges from {type(data).__name__}. Pass a GeoDataFrame, RoadEdges, "
        "file path, GeoJSON mapping, pyarrow Table, or DuckDB relation — or use "
        "roadstyle.from_duckdb()/from_arrow()/from_geojson()/load_edges() for full control."
    )
