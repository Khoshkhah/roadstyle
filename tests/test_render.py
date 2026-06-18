"""Smoke-test the folium renderer (lonboard is optional / GPU, skipped if absent)."""
import geopandas as gpd
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


# ---- direction arrows --------------------------------------------------------------
def test_render_with_arrows_returns_map():
    import folium
    m = render_edges(_edges(), arrows=True)                 # defaults: gray, zoom-gated
    assert isinstance(m, folium.Map)
    assert "getZoom()" in m.get_root().render()             # zoom-gate hook present by default


def test_chevron_features_one_per_edge():
    from roadstyle.arrows import chevron_features
    g = _edges()
    fc = chevron_features(g)
    assert len(fc["features"]) == len(g)                    # one chevron per LineString edge
    assert all(len(f["geometry"]["coordinates"]) == 3 for f in fc["features"])   # 3-point ">"


def test_chevron_features_where_col_filters():
    from roadstyle.arrows import chevron_features
    g = _edges().assign(oneway=[True, False, True, False])
    fc = chevron_features(g, where_col="oneway")
    assert len(fc["features"]) == 2                         # only the two oneway edges arrowed


def test_arrows_no_zoom_gate_when_min_zoom_none():
    m = render_edges(_edges(), arrows=True, arrow_min_zoom=None)
    assert "getZoom()" not in m.get_root().render()         # always-on, no zoomend hook
