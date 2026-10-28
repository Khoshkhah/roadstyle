"""Filtering the edges by road class."""
import geopandas as gpd
from shapely.geometry import LineString

from roadstyle import filter_edges, highway_types


def _edges():
    rows = [("motorway", LineString([(0, 0), (1, 1)])),
            ("residential", LineString([(1, 1), (2, 2)])),
            ("service", LineString([(2, 2), (3, 3)])),
            ("primary_link", LineString([(3, 3), (4, 4)]))]
    return gpd.GeoDataFrame({"highway": [r[0] for r in rows]},
                            geometry=[r[1] for r in rows], crs=4326)


def test_filter_include_exclude():
    g = _edges()
    assert set(filter_edges(g, include=["motorway", "residential"])["highway"]) == {
        "motorway",
        "residential",
    }
    assert "service" not in set(filter_edges(g, exclude="service")["highway"])
    # primary_link matches primary when match_links=True
    assert len(filter_edges(g, include="primary", match_links=True)) == 1
    assert len(filter_edges(g, include="primary", match_links=False)) == 0


def test_highway_types():
    assert set(highway_types(_edges())) == {"motorway", "residential", "service", "primary"}
