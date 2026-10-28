"""Smoke-test the folium renderer (lonboard is optional / GPU, skipped if absent)."""
from functools import partial as _partial

import geopandas as gpd
from shapely.geometry import LineString

from roadstyle import render_edges as _render_edges

# These tests exercise the folium backend specifically (legend/filter/arrows HTML, get_root()).
# The default backend is now "web" (MapLibre), so pin folium here; an explicit backend= still wins.
render_edges = _partial(_render_edges, backend="folium")


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






def test_lonboard_ignores_web_only_keywords():
    """Same as folium: a web-only keyword (view_3d, tiles, street_view) is dropped, not passed to
    lonboard.Map (which raised TypeError)."""
    import pytest
    pytest.importorskip("lonboard")
    m = _render_edges(_edges(), backend="lonboard", view_3d=True, tiles=True, street_view=False,
                      color_options={"Class": {}})
    assert m is not None










def test_unknown_basemap_raises():
    import pytest
    with pytest.raises(ValueError):
        render_edges(_edges(), basemap="nope")
