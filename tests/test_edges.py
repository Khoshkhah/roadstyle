"""Canonical input: RoadEdges normalization (CRS, geometry, column mapping)."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from roadstyle import RoadEdges, as_edges, normalize_edges, render_edges


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
    import folium

    e = normalize_edges(_raw(), rename={"vagtyp": "highway"})
    assert isinstance(render_edges(e), folium.Map)
    assert isinstance(render_edges(e.gdf), folium.Map)


def test_empty_raises_clear_error():
    g = _raw(4326).iloc[0:0]
    with pytest.raises(ValueError):
        normalize_edges(g)
