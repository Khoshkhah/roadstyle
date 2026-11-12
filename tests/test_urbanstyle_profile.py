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


# the four axes of the Granville file that are above the ground at a free end of the OSM bridge (the real bridge goes on past the end of the way): the axis and its distance along it where the
# free end is, and how high the axis is there (m): a2 at 403.9 m (4.5), a5 at 288.0 m (0.6), a6 at 28.8 m (0.9) and a8 at 184.0 m (8.3)
_RAISED = {"a2": 403.9, "a5": 288.0, "a6": 28.8, "a8": 184.0}


@pytest.fixture(scope="module")
def raw_bridge():
    """The file as urbanstyle wrote it."""
    return json.loads((SAMPLES / "granville_urbanstyle_axes.json").read_text())


@pytest.fixture(scope="module")
def bridge(raw_bridge):
    """The same file with the four raised axes brought down to the ground at their free end: no height within 10 m of it, and a rise over the next 30 m (what the file would say if the OSM bridge were as
    long as the real one). Every other axis is as urbanstyle wrote it."""
    out = copy.deepcopy(raw_bridge)
    for ax in out["axes"]:
        if ax["id"] in _RAISED:
            end, v = _RAISED[ax["id"]], ax["vertical"]
            for k in ("points", "samples"):
                v[k] = [[s, z * min(1.0, max(0.0, (abs(s - end) - 10.0) / 30.0))] for s, z in v[k]]
    return out


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
    assert sum(1 for n in nodes.values() if n["z_m"] == 0.0) == 8, nodes                  # the 8 free ends are on the ground


def test_an_axis_that_is_above_the_ground_at_a_free_end_is_an_error_that_names_every_such_end(edges, raw_bridge):
    """The Granville file as urbanstyle wrote it: the axes go on past the end of the OSM bridge, so four free ends are 0.6 m to 8.3 m above the ground. The converter does not set them to 0 (the deck
    would drop to the ground in a few metres): it stops, and names each node, its axis and the height."""
    with pytest.raises(ValueError) as e:
        _quiet(rs.bridge_profile_from_urbanstyle, edges, raw_bridge)
    msg = str(e.value)
    assert "above the ground at 4 free ends" in msg, msg
    for node, axis, z in (("n1", "a6", "0.9"), ("n2", "a8", "8.3"), ("n3", "a5", "0.6"), ("n13", "a2", "4.5")):
        assert f"{node} (the axis {axis} is {z} m high)" in msg, msg
    assert "does not set such an end to 0" in msg and "Fix the roads" in msg


def test_a_free_end_within_half_a_metre_of_the_ground_is_on_it(edges, bridge):
    near = copy.deepcopy(bridge)
    ax = next(a for a in near["axes"] if a["id"] == "a7")                        # 0.2 m high at its free end n9 in the file
    assert any(0 < z < 0.5 for _, z in ax["vertical"]["samples"][-3:]), ax["vertical"]["samples"][-3:]
    given = _quiet(rs.bridge_profile_from_urbanstyle, edges, near)
    assert next(n["z_m"] for n in given["groups"][0]["nodes"] if n["id"] == "n9") == 0.0


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


def test_the_converter_says_that_the_heights_are_above_urbanstyles_own_ground(edges, bridge):
    with pytest.warns(UserWarning, match="above urbanstyle's own reference ground"):
        given = rs.bridge_profile_from_urbanstyle(edges, bridge)
    assert "ground" not in given


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
