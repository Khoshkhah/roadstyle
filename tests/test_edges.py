"""Canonical input: RoadEdges normalization (CRS, geometry, column mapping)."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from roadstyle import (
    RoadEdges,
    as_edges,
    from_arrow,
    from_duckdb,
    from_geojson,
    normalize_edges,
    render_edges,
)


def _raw(crs=3857):
    return gpd.GeoDataFrame(
        {"vagtyp": ["motorway", "primary"], "aadt": [20000, 3000]},
        geometry=[LineString([(0, 0), (1000, 1000)]),
                  LineString([(1000, 1000), (2000, 1500)])],
        crs=crs,
    )


def test_normalize_reprojects_to_4326():
    e = normalize_edges(_raw(3857))
    assert isinstance(e, RoadEdges)
    assert e.gdf.crs.to_epsg() == 4326


def test_normalize_already_4326_is_skipped():
    g = _raw(4326)
    e = normalize_edges(g)
    assert e.gdf.crs.to_epsg() == 4326


def test_normalize_renames_class_column():
    e = normalize_edges(_raw(), class_col="highway", rename={"vagtyp": "highway"})
    assert "highway" in e.columns and e.class_col == "highway"


def test_normalize_drops_non_line_geometry():
    g = _raw(4326)
    pt = gpd.GeoDataFrame({"vagtyp": ["x"], "aadt": [0]}, geometry=[Point(5, 5)], crs=4326)
    g = pd.concat([g, pt]).pipe(gpd.GeoDataFrame, crs=4326)
    with pytest.warns(UserWarning):
        e = normalize_edges(g)
    assert len(e) == 2


def test_as_edges_passthrough_and_coerce():
    g = _raw(4326)
    e = normalize_edges(g)
    assert as_edges(e) is e                       # already canonical -> unchanged
    assert isinstance(as_edges(g), RoadEdges)     # plain gdf -> coerced


def test_render_accepts_roadedges_and_gdf():
    from roadstyle.render_web import WebMap

    e = normalize_edges(_raw(), rename={"vagtyp": "highway"})
    # default backend is now "web" (MapLibre) -> a WebMap; both input kinds are accepted
    assert isinstance(render_edges(e), WebMap)
    assert isinstance(render_edges(e.gdf), WebMap)


def test_empty_raises_clear_error():
    g = _raw(4326).iloc[0:0]
    with pytest.raises(ValueError):
        normalize_edges(g)


# ── wider inputs (Lever 1): path / GeoJSON / Arrow / DuckDB all reach the canonical shape ──────

def _named():  # a 4326 gdf whose class column is already "highway"
    return normalize_edges(_raw(4326), rename={"vagtyp": "highway"}).gdf


def test_as_edges_from_file_path(tmp_path):
    p = tmp_path / "edges.geojson"
    _named().to_file(p, driver="GeoJSON")
    e = as_edges(str(p))
    assert isinstance(e, RoadEdges) and len(e) == 2 and e.gdf.crs.to_epsg() == 4326


def test_as_edges_from_geojson_dict():
    import json

    fc = json.loads(_named().to_json())
    e = as_edges(fc)
    assert isinstance(e, RoadEdges) and len(e) == 2 and "highway" in e.columns


def test_from_geojson_accepts_a_spec_dict():
    from roadstyle import to_spec

    e = from_geojson(to_spec(_named()))     # a roadstyle to_spec() dict round-trips back in
    assert isinstance(e, RoadEdges) and len(e) == 2


def test_from_arrow_decodes_wkb():
    pa = pytest.importorskip("pyarrow")
    g = _named()
    table = pa.table({
        "highway": g["highway"].tolist(),
        "aadt": g["aadt"].tolist(),
        "geometry": [geom.wkb for geom in g.geometry],
    })
    e = from_arrow(table, geometry="geometry", crs=4326)
    assert isinstance(e, RoadEdges) and len(e) == 2 and "highway" in e.columns


def test_from_duckdb_wkb():
    duckdb = pytest.importorskip("duckdb")
    g = _named()
    con = duckdb.connect()
    con.execute("CREATE TABLE roads (highway VARCHAR, aadt INTEGER, geom BLOB)")
    for _, row in g.iterrows():
        con.execute("INSERT INTO roads VALUES (?, ?, ?)",
                    [row["highway"], int(row["aadt"]), row.geometry.wkb])
    e = from_duckdb(con, "SELECT highway, aadt, geom FROM roads", geometry="geom", crs=4326)
    assert isinstance(e, RoadEdges) and len(e) == 2 and "highway" in e.columns


def test_as_edges_unsupported_input_raises():
    with pytest.raises(TypeError):
        as_edges(12345)
