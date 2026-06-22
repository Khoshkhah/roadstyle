"""Per-edge colour table (edge_id -> colour) + colors='self' literal colouring."""
import json
import re

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
    geo = json.loads(re.search(r'"data":\s*(\{.*?\}),\s*"generateId"', html, re.S).group(1))
    return {f["properties"]["edge_id"]: f["properties"] for f in geo["features"]}


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
    p = _props(rs.render_edges(_edges(), color_table={"a": "#ff0000"}).html)
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
