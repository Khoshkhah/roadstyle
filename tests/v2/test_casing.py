"""Unit tests for roadstyle v2 2-point casing splitting engine."""

import math
from shapely.geometry import LineString
import pytest

from roadstyle.v2.engine.casing import split_casing_geometry
from roadstyle.v2.engine.primitives import Corridor, Channel, Demarcation, Patch, Glyph, ViewPreset


def _m_len(coords):
    """Rough length in meters around lat 59."""
    ls = LineString(coords)
    return ls.length * 111320.0 * math.cos(math.radians(59.0))


def test_primitives_instantiation():
    c = Corridor(
        geometry=LineString([(18.0, 59.0), (18.001, 59.0)]),
        width_m=10.0,
        casing_left_m=0.30,
        casing_right_m=0.10,
        split_start=8.0,
        split_end=12.0,
    )
    assert c.casing_m == 0.20
    assert c.split_start == 8.0
    assert c.split_end == 12.0

    ch = Channel(geometry=LineString([(18.0, 59.0), (18.001, 59.0)]), width_m=3.5)
    assert ch.interactive is True

    d = Demarcation(geometry=LineString([(18.0, 59.0), (18.001, 59.0)]), dash_array=[3, 9])
    assert d.interactive is False

    vp = ViewPreset(
        name="Traffic Congestion",
        width_mode="flow",
        width_by="aadt",
        color_by="v_over_c",
        cmap="plasma",
        label_by="speed_kmh",
    )
    assert vp.width_mode == "flow"
    assert vp.width_by == "aadt"
    assert vp.color_by == "v_over_c"



def test_symmetric_setbacks_splits_into_three_pieces():
    # Long line: d = 0.001 degrees lon at lat 59 is ~57.3m
    coords = [[18.0, 59.0], [18.001, 59.0]]
    pieces = split_casing_geometry(
        coords,
        split_start=5.0,
        split_end=5.0,
        split_mode="setbacks",
        casing_levels=(-1, 0, -2),
        properties={"road_id": 42},
    )
    assert len(pieces) == 3

    # Check casing levels
    assert [p["properties"]["__rs_cl"] for p in pieces] == [-1, 0, -2]

    # Check butt cap on middle piece only
    assert pieces[0]["properties"].get("__rs_cap") is None
    assert pieces[1]["properties"].get("__rs_cap") is True
    assert pieces[2]["properties"].get("__rs_cap") is None

    # Check approximate lengths
    l0 = _m_len(pieces[0]["geometry"]["coordinates"])
    l1 = _m_len(pieces[1]["geometry"]["coordinates"])
    l2 = _m_len(pieces[2]["geometry"]["coordinates"])
    assert abs(l0 - 5.0) < 0.2
    assert abs(l2 - 5.0) < 0.2
    assert abs(l1 - 47.3) < 0.5


def test_asymmetric_setbacks_different_cut_numbers():
    # Long line: ~57.3m
    coords = [[18.0, 59.0], [18.001, 59.0]]
    # Asymmetric: 15m at start (roundabout), 4m at end (T-junction)
    pieces = split_casing_geometry(
        coords,
        split_start=15.0,
        split_end=4.0,
        split_mode="setbacks",
        casing_levels=(1, 2, 3),
    )
    assert len(pieces) == 3
    l0 = _m_len(pieces[0]["geometry"]["coordinates"])
    l1 = _m_len(pieces[1]["geometry"]["coordinates"])
    l2 = _m_len(pieces[2]["geometry"]["coordinates"])

    assert abs(l0 - 15.0) < 0.3
    assert abs(l2 - 4.0) < 0.3
    assert abs(l1 - (57.3 - 19.0)) < 0.5


def test_short_road_heads_meet_proportionally():
    # Short line: 0.0001 deg is ~5.73m
    coords = [[18.0, 59.0], [18.0001, 59.0]]
    # Setbacks (5.0, 5.0) exceed total length 5.73m -> should split into 2 halves
    pieces = split_casing_geometry(
        coords,
        split_start=5.0,
        split_end=5.0,
        split_mode="setbacks",
        casing_levels=(-1, 0, -2),
    )
    assert len(pieces) == 2
    assert [p["properties"]["__rs_cl"] for p in pieces] == [-1, -2]
    # No piece has __rs_cap
    assert not any(p["properties"].get("__rs_cap") for p in pieces)

    l0 = _m_len(pieces[0]["geometry"]["coordinates"])
    l1 = _m_len(pieces[1]["geometry"]["coordinates"])
    assert abs(l0 - l1) < 0.1  # Equal halves


def test_stations_mode_absolute_cut_distances():
    coords = [[18.0, 59.0], [18.001, 59.0]]  # ~57.3m
    pieces = split_casing_geometry(
        coords,
        split_start=10.0,
        split_end=45.0,
        split_mode="stations",
        casing_levels=(10, 20, 30),
    )
    assert len(pieces) == 3
    assert [p["properties"]["__rs_cl"] for p in pieces] == [10, 20, 30]

    l0 = _m_len(pieces[0]["geometry"]["coordinates"])
    l1 = _m_len(pieces[1]["geometry"]["coordinates"])
    l2 = _m_len(pieces[2]["geometry"]["coordinates"])

    assert abs(l0 - 10.0) < 0.2
    assert abs(l1 - 35.0) < 0.4
    assert abs(l2 - (57.3 - 45.0)) < 0.4


def test_equal_casing_levels_returns_unsplit():
    coords = [[18.0, 59.0], [18.001, 59.0]]
    pieces = split_casing_geometry(
        coords,
        split_start=5.0,
        split_end=5.0,
        casing_levels=(2, 2, 2),
    )
    assert len(pieces) == 1
    assert pieces[0]["properties"]["__rs_cl"] == 2
    assert pieces[0]["geometry"]["coordinates"] == coords
