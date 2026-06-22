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


def test_folium_render_returns_map():
    import folium
    m = render_edges(_edges(), backend="folium", theme="dark")
    assert isinstance(m, folium.Map)


def test_folium_render_all_themes_and_palettes():
    import folium
    for theme in ("light", "dark", "satellite"):
        for palette in ("highsat", "carto"):
            m = render_edges(_edges(), theme=theme, palette=palette)
            assert isinstance(m, folium.Map)


def test_render_with_filter():
    import folium
    m = render_edges(_edges(), include=["motorway", "trunk"])
    assert isinstance(m, folium.Map)


def test_render_with_selection():
    import folium
    g = _edges()
    m = render_edges(g, selected=g[g["highway"] == "motorway"])
    assert isinstance(m, folium.Map)


def test_basemap_override_and_toggleable_basemaps():
    import folium

    from roadstyle import BASEMAPS
    assert {"positron", "dark_matter", "satellite", "voyager", "osm"} <= set(BASEMAPS)
    # single override
    m = render_edges(_edges(), basemap="voyager")
    assert isinstance(m, folium.Map)
    # multiple toggleable base layers
    m2 = render_edges(_edges(), basemaps=["positron", "dark_matter", "satellite"])
    assert isinstance(m2, folium.Map)


def test_unknown_basemap_raises():
    import pytest
    with pytest.raises(ValueError):
        render_edges(_edges(), basemap="nope")
