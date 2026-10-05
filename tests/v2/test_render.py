"""Unit tests for high-level roadstyle.v2.render facade."""

import geopandas as gpd
from pathlib import Path
import pytest
from shapely.geometry import LineString, MultiLineString

import roadstyle.v2 as rs
from roadstyle.v2.engine.compiler import WebMap


def test_render_shapely_lines():
    lines = [
        LineString([(0, 0), (100, 0)]),
        LineString([(100, 0), (100, 100)]),
    ]
    m = rs.render(
        lines,
        width=10.0,
        casing=0.30,
        color="#38bdf8",
        split_setback=6.0,
    )
    assert isinstance(m, WebMap)
    style = m.to_dict()
    assert "network" in style["sources"]
    assert len(style["layers"]) > 0


def test_render_geodataframe_categorical_color():
    gdf = gpd.GeoDataFrame(
        {
            "name": ["Highway 101", "Oak Ave", "Pine St"],
            "highway": ["motorway", "residential", "residential"],
            "lanes": [4, 2, 2],
            "speed": [110, 45, 50],
            "geometry": [
                LineString([(-122.4, 37.8), (-122.3, 37.8)]),
                LineString([(-122.35, 37.75), (-122.35, 37.85)]),
                LineString([(-122.38, 37.79), (-122.32, 37.79)]),
            ],
        }
    )

    palette = {"motorway": "#e11d48", "residential": "#0ea5e9"}
    m = rs.render(
        gdf,
        width="lanes",
        lane_width_m=3.5,
        color="highway",
        palette=palette,
        tooltip=["name", "speed", "lanes"],
    )

    assert isinstance(m, WebMap)
    style = m.to_dict()
    features = style["sources"]["network"]["data"]["features"]
    fill_features = [f for f in features if f["properties"].get("_type") == "corridor_fill"]
    assert len(fill_features) == 3

    # Check widths: 4 lanes -> 14.0m, 2 lanes -> 7.0m
    hw_feat = next(f for f in fill_features if f["properties"].get("name") == "Highway 101")
    res_feat = next(f for f in fill_features if f["properties"].get("name") == "Oak Ave")
    assert hw_feat["properties"]["width_m"] == 14.0
    assert hw_feat["properties"]["fill_color"] == "#e11d48"
    assert res_feat["properties"]["width_m"] == 7.0
    assert res_feat["properties"]["fill_color"] == "#0ea5e9"


def test_render_geodataframe_numeric_color_and_bridge():
    gdf = gpd.GeoDataFrame(
        {
            "speed": [20, 50, 100],
            "bridge": [False, False, True],  # One bridge road
            "geometry": [
                LineString([(0, 0), (50, 0)]),
                LineString([(50, 0), (100, 0)]),
                LineString([(25, -25), (25, 25)]),  # Crossing bridge
            ],
        }
    )

    m = rs.render(gdf, color="speed", palette="viridis", auto_solve=True)
    assert isinstance(m, WebMap)
    style = m.to_dict()
    features = style["sources"]["network"]["data"]["features"]
    fill_features = [f for f in features if f["properties"].get("_type") == "corridor_fill"]
    assert len(fill_features) == 3

    # Bridge should have higher fill level than ground road
    bridge_feat = fill_features[2]
    ground_feat = fill_features[0]
    assert bridge_feat["properties"]["level"] > ground_feat["properties"]["level"]


def test_render_multilinestring_unpacks():
    mls = MultiLineString([
        LineString([(0, 0), (10, 0)]),
        LineString([(10, 0), (20, 0)]),
    ])
    gdf = gpd.GeoDataFrame({"name": ["Split Route"], "geometry": [mls]})

    m = rs.render(gdf, width=8.0)
    style = m.to_dict()
    fill_features = [f for f in style["sources"]["network"]["data"]["features"] if f["properties"].get("_type") == "corridor_fill"]
    assert len(fill_features) == 2


def test_render_geojson_dict():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [10, 10]]},
                "properties": {"name": "Test Way", "width_m": 12.0},
            }
        ],
    }

    m = rs.render(fc)
    assert isinstance(m, WebMap)
    style = m.to_dict()
    assert "network" in style["sources"]
