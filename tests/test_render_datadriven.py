"""Data-driven rendering through render_edges (Phase 3 wiring)."""
import geopandas as gpd
import pytest
from shapely.geometry import LineString

from roadstyle import color_by_value, render_edges


def _edges():
    return gpd.GeoDataFrame(
        {"highway": ["motorway", "primary", "residential", "service"],
         "congestion": ["low", "moderate", "heavy", "severe"],
         "aadt": [25000, 8000, 1500, 100]},
        geometry=[LineString([(i, 0), (i + 1, 1)]) for i in range(4)], crs=4326)


def _html(m):
    return m.get_root().render()


def test_classic_path_unchanged():
    import folium
    m = render_edges(_edges(), theme="dark")
    assert isinstance(m, folium.Map)
    # OSM interactive layer is used when no data-driven args are given
    assert "InteractiveRoads" in _html(m)


def test_categorical_render_embeds_colors():
    m = render_edges(_edges(), color_by="congestion",
                     colors={"low": "#11D68F", "moderate": "#FFCF43",
                             "heavy": "#F24E42", "severe": "#A92727"})
    html = _html(m)
    for c in ("#11D68F", "#FFCF43", "#F24E42", "#A92727"):
        assert c in html
    # data-driven path does NOT use the OSM interactive layer
    assert "InteractiveRoads" not in html
    assert "__rs_fill" in html


def test_numeric_render_with_width_ramp():
    m = render_edges(_edges(), color_by="aadt", cmap="viridis", width_by=(1, 8))
    html = _html(m)
    assert "__rs_w" in html
    assert "#fde725" in html.lower()      # viridis high end (yellow)


def test_explicit_styler_object():
    import folium
    m = render_edges(_edges(), style=color_by_value("aadt", cmap="magma"))
    assert isinstance(m, folium.Map)


def test_missing_color_by_column_raises():
    with pytest.raises(ValueError):
        render_edges(_edges(), color_by="nope", colors={"x": "#fff"})


def test_lonboard_data_driven():
    lonboard = pytest.importorskip("lonboard")
    m = render_edges(_edges(), backend="lonboard", color_by="aadt", cmap="magma")
    assert isinstance(m, lonboard.Map)
    assert len(m.layers) == 2             # casing + fill sandwich
