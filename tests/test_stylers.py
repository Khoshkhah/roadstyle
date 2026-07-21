"""Data-driven stylers: categorical + numeric coloring, and the styler selector."""
import geopandas as gpd
from shapely.geometry import LineString

from roadstyle import (
    CategoricalStyler,
    ClassStyler,
    NumericStyler,
    Styler,
    build_styler,
    color_by,
    color_by_value,
    resolve,
)


def _edges():
    return gpd.GeoDataFrame(
        {
            "highway": ["motorway", "primary_link", "residential", "service"],
            "congestion": ["low", "moderate", "heavy", None],
            "aadt": [0, 5000, 15000, None],
        },
        geometry=[LineString([(i, 0), (i + 1, 1)]) for i in range(4)],
        crs=4326,
    )


def test_class_styler_matches_resolve():
    g = _edges()
    rf = ClassStyler().resolve_frame(g)
    for i, hw in enumerate(g["highway"]):
        r = resolve(hw, palette="highsat")
        assert rf.fill[i] == r.fill
        assert abs(rf.width[i] - r.width) < 1e-9
        assert rf.casing[i] == r.casing


def test_categorical_styler_maps_and_falls_back():
    g = _edges()
    rf = CategoricalStyler(
        column="congestion",
        colors={"low": "#11D68F", "moderate": "#FFCF43", "heavy": "#F24E42"},
        fallback_color="#cccccc",
    ).resolve_frame(g)
    assert rf.fill == ["#11D68F", "#FFCF43", "#F24E42", "#cccccc"]
    assert rf.casing == [None] * 4          # data overlays carry no casing by default


def test_numeric_styler_ramp_endpoints_and_nan():
    g = _edges()
    rf = NumericStyler(column="aadt", cmap="viridis", vmin=0, vmax=15000).resolve_frame(g)
    # endpoints of viridis
    assert rf.fill[0].lower().startswith("#44")     # low end (dark purple)
    assert rf.fill[2].lower() == "#fde725"          # high end (yellow)
    assert rf.fill[3] == "#cccccc"                  # None -> nan_color
    assert rf.legend["kind"] == "continuous" and rf.legend["vmin"] == 0


def test_numeric_width_ramp():
    g = _edges()
    rf = NumericStyler(column="aadt", vmin=0, vmax=15000, width_by=(1, 9)).resolve_frame(g)
    assert abs(rf.width[0] - 1.0) < 0.3      # min aadt -> thin
    assert rf.width[2] > 8.0                  # max aadt -> thick


def test_build_styler_resolution_order():
    # default -> ClassStyler
    assert isinstance(build_styler(), ClassStyler)
    # color_by + colors -> CategoricalStyler
    assert isinstance(build_styler(color_by="congestion", colors={"low": "#fff"}),
                      CategoricalStyler)
    # color_by + cmap -> NumericStyler
    assert isinstance(build_styler(color_by="aadt", cmap="magma"), NumericStyler)
    # explicit style wins
    s = NumericStyler(column="aadt")
    assert build_styler(style=s) is s


def test_convenience_constructors_are_stylers():
    assert isinstance(color_by("congestion", {"low": "#fff"}), Styler)
    assert isinstance(color_by_value("aadt", cmap="viridis"), Styler)
