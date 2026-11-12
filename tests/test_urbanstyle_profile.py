"""The converter from an urbanstyle bridge file to an input profile (docs/design/bridge_profile_edit.md, step 5): an axis is a chain when they have the same OSM ways, and the heights of the axis
become the node heights and the grade points of the chain. The data is the Granville Bridge: its 41 roads and the 12 axes of urbanstyle's measured profile (City of Vancouver LiDAR 2022)."""
import copy
import json
import warnings
from pathlib import Path

import geopandas as gpd
import pytest

import roadstyle as rs

SAMPLES = Path(__file__).resolve().parents[1] / "docs" / "samples" / "bridge-profile"


@pytest.fixture(scope="module")
def edges():
    return gpd.read_parquet(SAMPLES / "granville_bridge_edges.parquet")


@pytest.fixture(scope="module")
def bridge():
    return json.loads((SAMPLES / "granville_urbanstyle_axes.json").read_text())


def _quiet(f, *a, **k):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return f(*a, **k)


def test_the_12_axes_of_the_granville_bridge_are_the_12_chains_and_give_the_heights_of_the_lidar(edges, bridge):
    given = _quiet(rs.bridge_profile_from_urbanstyle, edges, bridge)
    assert given["parameters"] == {"curve": "design"}
    nodes = {n["id"]: n for n in given["groups"][0]["nodes"]}
    assert len(nodes) == 13 and len(given["groups"][0]["chains"]) == 12
    # the five junctions are the five heights of the LiDAR file: 27.0 m, 22.7 m, 18.2 m, 11.7 m and 11.6 m
    junction = sorted(n["z_m"] for n in nodes.values() if n["z_m"] > 10)
    assert junction == pytest.approx([11.62, 11.74, 18.19, 22.71, 27.04], abs=0.05), junction
    assert all(n["source"] == "City of Vancouver LiDAR 2022" and n["method"] == "measured" for n in nodes.values())
    # the free ends that the LiDAR finds above the ground: the deck goes on to the street on fill past the end of the OSM bridge way
    assert sorted(round(n["z_m"], 1) for n in nodes.values() if n["z_m"] < 10 and n["z_m"] > 4) == [4.5, 8.3]


def test_the_profile_is_complete_through_the_engine_and_the_decks_follow_the_lidar(edges, bridge):
    given = _quiet(rs.bridge_profile_from_urbanstyle, edges, bridge)
    p = _quiet(rs.bridge_profile, edges, bridge_profile=given)
    assert p["parameters"]["curve"] == "design" and _quiet(rs.bridge_profile, edges, bridge_profile=p) == p            # the filler twice is the filler once
    tops = sorted(round(c["top_m"], 1) for g in p["groups"] for c in g["chains"])
    assert tops[-1] == pytest.approx(39.3, abs=0.2) and tops[0] == pytest.approx(11.6, abs=0.2), tops               # the main span peaks at 39.3 m; the lowest ramp tops out at 11.6 m
    # the longest chain is the main span (axis a1, 550 m, no landing past either end): the engine's height along it is the axis's height within a metre
    c1 = next(c for g in p["groups"] for c in g["chains"] if c["id"] == "c1")
    z = {n["id"]: n["z_m"] for g in p["groups"] for n in g["nodes"]}
    axis = next(a for a in bridge["axes"] if a["id"] == "a1")
    pts = [(0.0, z[c1["from"]])] + [(q["s"], q["z_m"]) for q in c1["points"]] + [(c1["length_m"], z[c1["to"]])]
    err = 0.0
    for s, zz in axis["vertical"]["samples"]:
        if 0 <= s <= c1["length_m"]:
            i = max(k for k in range(len(pts) - 1) if pts[k][0] <= s)
            zl = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * (s - pts[i][0]) / (pts[i + 1][0] - pts[i][0])      # the grade points, straight (the curves round them by under a metre)
            err = max(err, abs(zl - zz))
    assert err < 1.0, err


def test_the_page_draws_the_converted_profile(edges, bridge):
    given = _quiet(rs.bridge_profile_from_urbanstyle, edges, bridge)
    html = _quiet(rs.render_edges, edges, backend="web", view_3d=True, bridge_profile=given).html
    assert "__rs_lift0" in html


def test_an_axis_that_is_not_for_these_roads_and_a_chain_with_no_axis_are_errors_that_say_so(edges, bridge):
    other = copy.deepcopy(bridge)
    other["axes"][0]["ways"] = ["w1"]
    with pytest.raises(ValueError, match="no axis with the same OSM ways"):
        _quiet(rs.bridge_profile_from_urbanstyle, edges, other)
    with pytest.raises(ValueError, match="urbanstyle.bridge/1"):
        _quiet(rs.bridge_profile_from_urbanstyle, edges, {**bridge, "format": "other"})
    with pytest.raises(ValueError, match="no column 'way'"):
        _quiet(rs.bridge_profile_from_urbanstyle, edges, bridge, way_col="way")
    flat = edges.assign(bridge=None)
    with pytest.raises(ValueError, match="no 3D bridges"):
        _quiet(rs.bridge_profile_from_urbanstyle, flat, bridge)


def test_an_axis_with_no_chain_is_a_warning_and_a_node_that_two_axes_set_differently_gets_the_mean(edges, bridge):
    extra = copy.deepcopy(bridge)
    extra["axes"].append({**copy.deepcopy(extra["axes"][0]), "id": "a99", "ways": ["w1"]})
    with pytest.warns(UserWarning, match="axis a99"):
        rs.bridge_profile_from_urbanstyle(edges, extra)
    moved = copy.deepcopy(bridge)
    for k in ("points", "samples"):
        moved["axes"][0]["vertical"][k] = [[s, z + 5.0] for s, z in moved["axes"][0]["vertical"][k]]
    with pytest.warns(UserWarning, match="differ by"):
        rs.bridge_profile_from_urbanstyle(edges, moved)
