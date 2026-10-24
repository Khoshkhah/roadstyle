"""Per-edge colour table (edge_id -> colour) + colors='self' literal colouring."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString

import roadstyle as rs


def _edges():
    return gpd.GeoDataFrame(
        {"edge_id": ["a", "b", "c", "d"],
         "highway": ["motorway", "primary", "residential", "service"]},
        geometry=[LineString([(i, 0), (i + 1, 0)]) for i in range(4)], crs=4326)


def _props(html):
    """Each road's properties from the page's road table (a page has no roads source)."""
    from road_table import roads_of
    return {f["properties"]["edge_id"]: f["properties"] for f in roads_of(html)["features"]}


def test_color_table_dict_with_gray_fallback():
    p = _props(rs.render_edges(_edges(), color_table={"a": "#ff0000", "c": "#00ff00"}).html)
    fills = {k: v["__rs_fill"] for k, v in p.items()}
    assert fills == {"a": "#ff0000", "b": "#bbbbbb", "c": "#00ff00", "d": "#bbbbbb"}


def test_color_table_dataframe():
    df = pd.DataFrame({"edge_id": ["b", "d"], "color": ["#0000ff", "#ffff00"]})
    p = _props(rs.render_edges(_edges(), color_table=df).html)
    assert p["b"]["__rs_fill"] == "#0000ff" and p["d"]["__rs_fill"] == "#ffff00"
    assert p["a"]["__rs_fill"] == "#bbbbbb"


def test_color_table_keeps_casing_sandwich():
    # fill comes from the table; casing stays class/theme so junctions still read cleanly
    geo = rs.render_edges(_edges(), backend="web", color_table={"a": "#ff0000"}, _palette_copy=True)["geo"]      # the roads with their stage values
    p = {f["properties"]["edge_id"]: f["properties"] for f in geo["features"]}
    assert p["a"]["__rs_casing"] not in (None, "#bbbbbb")


def test_colors_self_literal_column():
    g = _edges().assign(color=["#111111", None, "#222222", "red"])
    fills = {k: v["__rs_fill"] for k, v in _props(
        rs.render_edges(g, color_by="color", colors="self").html).items()}
    assert fills["a"] == "#111111" and fills["b"] == "#bbbbbb" and fills["d"] == "red"


def test_color_table_folium_returns_map():
    import folium
    assert isinstance(rs.render_edges(_edges(), backend="folium",
                                      color_table={"a": "#ff0000"}), folium.Map)


def test_bad_color_table_raises():
    with pytest.raises(ValueError):
        rs.render_edges(_edges(), color_table=pd.DataFrame({"x": [1]}))   # no edge_id/color cols


def test_a_missing_category_is_empty_text_in_both_engines():
    """A missing category (None or NaN: pandas gives either, by its version) has the class text "" in both engines, on every Python
    version (2026-10-24: Python 3.10's pandas gave "" and Rust "nan")."""
    import math

    from roadstyle.stylers import _keystr

    assert _keystr(None) == _keystr(math.nan) == _keystr(float("nan")) == "" and _keystr(" Primary ") == "primary"
    g = _edges().assign(cat=pd.Series(["x", None, math.nan, "y"], dtype=object))
    kw = {"color_by": "cat", "colors": {"x": "#ff0000", "y": "#0000ff"}}
    geo = rs.render_edges(g, backend="web", _palette_copy=True, **kw)["geo"]          # the roads with their stage values
    assert [f["properties"]["__rs_class"] for f in geo["features"]] == ["x", "", "", "y"]
    py, rust = (rs.export_inline(g, engine=e, **kw) for e in ("python", "rust"))
    assert py == rust
