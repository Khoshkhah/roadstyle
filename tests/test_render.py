"""render_edges: a removed backend (folium, lonboard) and an unknown base map are errors with a clear message."""
import geopandas as gpd
import pytest
from shapely.geometry import LineString

from roadstyle import render_edges


def _edges():
    return gpd.GeoDataFrame(
        {"highway": ["motorway", "trunk", "residential", "service"],
         "name": ["E18", "Rv275", "Main St", "Alley"]},
        geometry=[LineString([(17.9, 59.37), (17.91, 59.38)]),
                  LineString([(17.91, 59.38), (17.92, 59.38)]),
                  LineString([(17.92, 59.38), (17.92, 59.39)]),
                  LineString([(17.92, 59.39), (17.93, 59.39)])],
        crs=4326,
    )


@pytest.mark.parametrize("backend", ["folium", "lonboard"])
def test_a_removed_backend_is_an_error(backend):
    with pytest.raises(ValueError, match="the only backend is 'web'"):
        render_edges(_edges(), backend=backend)


def test_unknown_basemap_raises():
    with pytest.raises(ValueError, match="nope"):
        render_edges(_edges(), basemap="nope")
