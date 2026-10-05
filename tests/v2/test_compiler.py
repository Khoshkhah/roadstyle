"""Unit tests for roadstyle v2 WebGL Style Compiler."""

import json
from pathlib import Path
import pytest
from shapely.geometry import LineString, Point, Polygon

from roadstyle.v2.engine.compiler import (
    WebMap,
    compile_map,
    lateral_offset_expr,
    meter_to_pixel_width_expr,
)
from roadstyle.v2.engine.primitives import (
    Channel,
    Corridor,
    Demarcation,
    Glyph,
    Patch,
    ViewPreset,
)


def test_meter_to_pixel_width_expression():
    expr = meter_to_pixel_width_expr("width_m", min_px=1.25)
    # MapLibre requires zoom interpolation to be top-level
    assert expr[0] == "interpolate"
    assert expr[1] == ["exponential", 2]
    assert expr[2] == ["zoom"]
    # Check zoom 10 stop is clamped: ['max', 1.25, ['*', ['get', 'width_m'], 0.051]]
    assert expr[4][0] == "max"
    assert expr[4][1] == 1.25

    # With casing extra width (W + 2 * C)
    casing_expr = meter_to_pixel_width_expr("width_m", extra_prop="casing_m")
    assert casing_expr[0] == "interpolate"
    zoom_10_term = casing_expr[4]
    assert zoom_10_term[0] == "max"
    assert zoom_10_term[2][0] == "*"
    assert zoom_10_term[2][1][0] == "+"


def test_lateral_offset_expression():
    expr = lateral_offset_expr("casing_left_m", "casing_right_m")
    assert expr[0] == "interpolate"
    # Check difference calculation
    zoom_10_term = expr[4]
    assert zoom_10_term[1] == ["-", ["coalesce", ["get", "casing_left_m"], 0.0], ["coalesce", ["get", "casing_right_m"], 0.0]]


def test_single_source_integrity():
    # Define a network with multiple primitives
    corridor = Corridor(
        geometry=LineString([(0, 0), (100, 0)]),
        width_m=10.0,
        casing_left_m=0.3,
        casing_right_m=0.15,
        fill_visible=True,
    )
    channel = Channel(
        geometry=LineString([(0, 0), (100, 0)]),
        width_m=3.5,
        color="#3b82f6",
    )
    demarcation = Demarcation(
        geometry=LineString([(0, 0), (100, 0)]),
        width_m=0.15,
        pattern="dashed",
    )
    patch = Patch(
        geometry=Polygon([(-5, -5), (5, -5), (5, 5), (-5, 5)]),
        color="#15803d",
        order=-1,
    )
    glyph = Glyph(
        geometry=Point(50, 0),
        text="Main St",
    )

    m = compile_map(
        corridors=[corridor],
        channels=[channel],
        demarcations=[demarcation],
        patches=[patch],
        glyphs=[glyph],
        auto_solve=True,
    )

    style = m.to_dict()

    # 1. Exactly ONE network GeoJSON source
    assert "network" in style["sources"]
    assert style["sources"]["network"]["type"] == "geojson"

    # Basemap is separate raster/vector tile, but all geometric primitives live in "network"
    geom_sources = [k for k, v in style["sources"].items() if v.get("type") == "geojson"]
    assert geom_sources == ["network"]

    # 2. All vector layers point to the single "network" source
    for lay in style["layers"]:
        if lay["type"] not in ("raster", "background"):
            assert lay["source"] == "network", f"Layer {lay['id']} does not use network source"


def test_auto_solve_integration():
    c1 = Corridor(
        geometry=LineString([(-50, 0), (50, 0)]),
        band=0,
    )
    c2 = Corridor(
        geometry=LineString([(0, -50), (0, 50)]),
        band=1,  # Bridge
    )
    assert c1.casing_levels is None
    assert c2.fill_level is None

    m = compile_map(corridors=[c1, c2], auto_solve=True)

    # Corridors should now have computed integer levels
    assert c1.casing_levels is not None
    assert c1.fill_level is not None
    assert c2.fill_level > c1.fill_level


def test_html_export_and_repr(tmp_path: Path):
    corridor = Corridor(geometry=LineString([(0, 0), (50, 50)]), width_m=8.0)
    presets = [
        ViewPreset(name="Physical", width_mode="physical"),
        ViewPreset(name="Volume Flow", width_mode="flow", width_by="volume"),
    ]

    m = compile_map(corridors=[corridor], presets=presets)

    # 1. to_style_json()
    style_json = m.to_style_json()
    parsed = json.loads(style_json)
    assert parsed["version"] == 8

    # 2. save(filepath)
    out_file = tmp_path / "test_map.html"
    saved_path = m.save(out_file)
    assert Path(saved_path).exists()
    content = Path(saved_path).read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "maplibregl" in content
    assert "Volume Flow" in content

    # 3. _repr_html_()
    iframe = m._repr_html_()
    assert "<iframe" in iframe
    assert "srcdoc=" in iframe


def test_bridge_and_tunnel_compilation():
    surface_road = Corridor(
        geometry=LineString([(0, 50), (100, 50)]),
        width_m=8.0,
        band=0,
    )
    bridge_road = Corridor(
        geometry=LineString([(50, 0), (50, 100)]),
        width_m=10.0,
        band=1,
        bridge_deck=True,
    )
    tunnel_road = Corridor(
        geometry=LineString([(0, 20), (100, 20)]),
        width_m=8.0,
        band=-1,
        tunnel=True,
    )

    m = compile_map(corridors=[surface_road, bridge_road, tunnel_road], auto_solve=True)
    style = m.style
    layers = style["layers"]
    layer_ids = [l["id"] for l in layers]

    # Verify bridge shadow layers exist
    bridge_shadow_layers = [l for l in layers if l["id"].startswith("bridge-shadow-")]
    assert len(bridge_shadow_layers) > 0
    b_shadow = bridge_shadow_layers[0]
    assert b_shadow["paint"]["line-blur"] == 1.5
    assert b_shadow["layout"]["line-cap"] == "butt"

    # Verify tunnel dashed casing layers exist
    tunnel_dash_layers = [l for l in layers if l["id"].startswith("tunnel-casing-dash-")]
    assert len(tunnel_dash_layers) > 0
    t_dash = tunnel_dash_layers[0]
    assert t_dash["paint"]["line-dasharray"] == [3.0, 3.0]

    # Verify corridor fill has tunnel opacity expression
    corridor_fill_layers = [l for l in layers if l["id"].startswith("corridors-fill-")]
    assert len(corridor_fill_layers) > 0
    fill_layer = corridor_fill_layers[0]
    opacity_expr = fill_layer["paint"]["line-opacity"]
    assert opacity_expr[0] == "case"
    assert opacity_expr[1] == ["==", ["get", "tunnel"], True]
    assert opacity_expr[2] == 0.50

    # Verify GeoJSON source features contain bridge and tunnel properties
    features = style["sources"]["network"]["data"]["features"]
    bridge_features = [f for f in features if f["properties"].get("bridge") is True]
    tunnel_features = [f for f in features if f["properties"].get("tunnel") is True]
    assert len(bridge_features) > 0
    assert len(tunnel_features) > 0

