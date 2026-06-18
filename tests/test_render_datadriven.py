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


def test_classic_path_renders_baked_props():
    import folium
    m = render_edges(_edges(), theme="dark")
    assert isinstance(m, folium.Map)
    html = _html(m)
    # One folium path: the OSM class styling now also bakes per-edge __rs_* props (read by the
    # single InteractiveRoads layer), and its dynamic-casing hook is present.
    assert "__rsCasing" in html
    assert "__rs_fill" in html
    assert "__rs_class" in html        # class baked → drives the road-type filter panel


def test_categorical_render_embeds_colors():
    m = render_edges(_edges(), color_by="congestion",
                     colors={"low": "#11D68F", "moderate": "#FFCF43",
                             "heavy": "#F24E42", "severe": "#A92727"})
    html = _html(m)
    for c in ("#11D68F", "#FFCF43", "#F24E42", "#A92727"):
        assert c in html
    # data-driven path writes per-edge __rs_* props (the OSM InteractiveRoads layer does not)
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


def test_folium_pin_inlined_in_both_styling_modes():
    # The single folium path always wires up click-to-pin, regardless of styling mode.
    for kw in ({}, {"color_by": "aadt", "cmap": "viridis"}):
        html = _html(render_edges(_edges(), **kw))
        assert "rsPin" in html               # the pin handler
        assert "rs-tip-pinned" in html       # the pinned-tooltip class


def test_folium_filter_for_class_legend_for_data_driven():
    # Through the one InteractiveRoads layer: class styling shows the road-type filter (no legend);
    # a data-driven map shows a legend instead (no filter panel).
    class_html = _html(render_edges(_edges(), theme="dark"))
    assert "Road types" in class_html and "rs-legend" not in class_html
    num_html = _html(render_edges(_edges(), color_by="aadt", cmap="viridis"))
    assert "rs-legend" in num_html and "Road types" not in num_html


def test_lonboard_data_driven():
    lonboard = pytest.importorskip("lonboard")
    m = render_edges(_edges(), backend="lonboard", color_by="aadt", cmap="magma")
    assert isinstance(m, lonboard.Map)
    assert len(m.layers) == 2             # casing + fill sandwich
