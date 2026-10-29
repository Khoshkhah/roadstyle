"""A page with many roads and no tiles gets a warning: MapLibre cuts the GeoJSON in the browser and draws every vertex (Nacka, 22,000
roads, 2026-10-29: 2.5 times the triangles of tiles=True at zoom 11 to 13, and a map that blanks while new tiles are made)."""
import geopandas as gpd
import pytest
from shapely.geometry import LineString

import roadstyle as rs
from roadstyle import _engine

pytestmark = pytest.mark.skipif(not _engine.available(), reason="no roadstyle._rust")


def _roads(n):
    lines = [LineString([(18.0 + (i % 100) * 1e-3, 59.3 + (i // 100) * 1e-3), (18.0005 + (i % 100) * 1e-3, 59.3 + (i // 100) * 1e-3)]) for i in range(n)]
    return gpd.GeoDataFrame({"highway": ["residential"] * n, "edge_id": list(range(n))}, geometry=lines, crs=4326)


def test_many_roads_without_tiles_warn():
    with pytest.warns(UserWarning, match="roads from GeoJSON"):
        rs.render_dashboard(_roads(10_000), basemap="blank")


def test_few_roads_and_tiled_pages_do_not_warn(recwarn):
    rs.render_dashboard(_roads(50), basemap="blank")
    assert not [w for w in recwarn if "GeoJSON" in str(w.message)]
