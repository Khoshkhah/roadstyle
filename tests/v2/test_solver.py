"""Unit tests for roadstyle v2 LP Stacking Solver."""

import pytest
from shapely.geometry import LineString

from roadstyle.v2.engine.primitives import Corridor
from roadstyle.v2.engine.solver import solve_stacking


def test_empty_corridors():
    sol = solve_stacking([])
    assert sol.status == "EMPTY"
    assert len(sol.casing_levels) == 0
    assert len(sol.fill_levels) == 0


def test_single_ground_corridor():
    c = Corridor(
        geometry=LineString([(0, 0), (100, 0)]),
        width_m=8.0,
        band=0,
    )
    sol = solve_stacking([c], assign=True)
    assert sol.status == "OPTIMAL"
    assert c.casing_levels == (0, 0, 0)
    assert c.fill_level == 0


def test_bridge_over_ground_road():
    # Ground road along X axis
    ground = Corridor(
        geometry=LineString([(-50, 0), (50, 0)]),
        width_m=10.0,
        band=0,
        split_start=5.0,
        split_end=5.0,
    )
    # Bridge road along Y axis crossing the ground road
    bridge = Corridor(
        geometry=LineString([(0, -50), (0, 50)]),
        width_m=12.0,
        band=1,  # Upper band
        split_start=5.0,
        split_end=5.0,
    )

    sol = solve_stacking([ground, bridge], margin=1.0, assign=True)
    assert sol.status == "OPTIMAL"

    # Bridge main casing must be above ground road fill
    cs_b, cm_b, ce_b = bridge.casing_levels
    fl_g = ground.fill_level
    fl_b = bridge.fill_level

    # Upper road fill must be strictly greater than lower road fill
    assert fl_b > fl_g
    # Upper road main casing must be >= lower road fill + margin
    assert cm_b >= fl_g + 1


def test_roundabout_ring_priority_dominance():
    # Junction at (10, 0)
    # Roundabout ring segment with high priority
    ring = Corridor(
        geometry=LineString([(0, 10), (10, 0)]),
        width_m=10.0,
        band=0,
        junction_priority=100.0,  # Roundabout ring flow
        split_start=4.0,
        split_end=4.0,
    )
    # Approach arm meeting the ring at (10, 0)
    arm = Corridor(
        geometry=LineString([(50, 0), (10, 0)]),
        width_m=8.0,
        band=0,
        junction_priority=0.0,  # Standard approach
        split_start=4.0,
        split_end=12.0,  # Entry setback
    )

    sol = solve_stacking([ring, arm], margin=1.0, assign=True)
    assert sol.status == "OPTIMAL"

    # Ring fill must paint strictly over arm fill
    assert ring.fill_level > arm.fill_level
    assert ring.fill_level >= arm.fill_level + 1

    # Arm's end casing at the junction must not exceed ring's fill
    cs_arm, cm_arm, ce_arm = arm.casing_levels
    assert ce_arm <= ring.fill_level


def test_multi_level_tunnel_surface_bridge():
    # 3 crossing roads at same spot
    tunnel = Corridor(
        geometry=LineString([(-50, 0), (50, 0)]),
        band=-1,  # Tunnel
        width_m=10.0,
        split_start=5.0,
        split_end=5.0,
    )
    surface = Corridor(
        geometry=LineString([(0, -50), (0, 50)]),
        band=0,  # Surface
        width_m=10.0,
        split_start=5.0,
        split_end=5.0,
    )
    bridge = Corridor(
        geometry=LineString([(-40, -40), (40, 40)]),
        band=1,  # Bridge
        width_m=12.0,
        split_start=5.0,
        split_end=5.0,
    )

    sol = solve_stacking([tunnel, surface, bridge], margin=1.0, assign=True)
    assert sol.status == "OPTIMAL"

    # Strict order: tunnel fill < surface fill < bridge fill
    assert tunnel.fill_level < surface.fill_level < bridge.fill_level
    # Bridge casing main >= surface fill + 1
    assert bridge.casing_levels[1] >= surface.fill_level + 1
    # Surface casing main >= tunnel fill + 1
    assert surface.casing_levels[1] >= tunnel.fill_level + 1


def test_t_junction_casing_blend():
    # Main road A from (0, 0) to (100, 0)
    # Side road B meeting main road at (100, 0) going to (100, 50)
    road_a = Corridor(
        geometry=LineString([(0, 0), (100, 0)]),
        band=0,
        junction_priority=10.0,
        split_start=5.0,
        split_end=5.0,
    )
    road_b = Corridor(
        geometry=LineString([(100, 0), (100, 50)]),
        band=0,
        junction_priority=0.0,
        split_start=5.0,
        split_end=5.0,
    )

    sol = solve_stacking([road_a, road_b], assign=True)
    assert sol.status == "OPTIMAL"

    # Road A has higher priority
    assert road_a.fill_level >= road_b.fill_level
    # Road B start casing (which touches road A) must not exceed road A fill
    assert road_b.casing_levels[0] <= road_a.fill_level


def test_different_bands_connected_at_junction():
    """Roads in different bands (e.g. ramp from ground to elevated bridge) can and do connect."""
    # Surface road (band 0) ending at (50, 0)
    ground = Corridor(
        geometry=LineString([(0, 0), (50, 0)]),
        width_m=8.0,
        band=0,
        split_start=5.0,
        split_end=5.0,
    )
    # Elevated bridge / ramp (band 1) starting at the same junction (50, 0)
    bridge_ramp = Corridor(
        geometry=LineString([(50, 0), (100, 0)]),
        width_m=10.0,
        band=1,
        split_start=5.0,
        split_end=5.0,
    )

    sol = solve_stacking([ground, bridge_ramp], margin=1.0, assign=True)
    assert sol.status == "OPTIMAL"

    # Bridge fill is higher than ground fill
    assert bridge_ramp.fill_level > ground.fill_level

    # But at the junction (50, 0), the bridge ramp's start casing must merge (<= ground fill)
    # so its casing outline does NOT cross into or over the ground road's fill
    cs_ramp, cm_ramp, ce_ramp = bridge_ramp.casing_levels
    assert cs_ramp <= ground.fill_level
    # Meanwhile, the bridge ramp's main casing is stacked above ground fill
    assert cm_ramp >= ground.fill_level + 1


def test_reverse_physical_twin_uses_one_result_and_reverses_heads():
    forward = Corridor(
        id="road-forward",
        geometry=LineString([(0, 0), (100, 0)]),
        band=0,
        properties={"edge_ref": "road-forward", "road_id": "road-1"},
    )
    reverse = Corridor(
        id="road-reverse",
        geometry=LineString([(100, 0), (0, 0)]),
        band=0,
        properties={"edge_ref": "road-reverse", "road_id": "road-1"},
    )
    bridge = Corridor(
        id="bridge",
        geometry=LineString([(50, -50), (50, 50)]),
        band=1,
        properties={"edge_ref": "bridge"},
    )
    pairs = [{
        "pair_id": "bridge-crosses-reverse-road",
        "relation": "cross",
        "edge_a": "bridge",
        "edge_b": "road-reverse",
        "node_ref": "",
        "endpoint_a": "",
        "endpoint_b": "",
        "upper_edge_ref": "bridge",
        "lower_edge_ref": "road-reverse",
        "enabled": "true",
    }]

    solution = solve_stacking([forward, reverse, bridge], pair_table=pairs, margin=1)

    assert solution.info["direction_twin_count"] == 1
    assert solution.casing_levels[1] == tuple(reversed(solution.casing_levels[0]))
    assert solution.fill_levels[1] == solution.fill_levels[0]
    assert solution.casing_levels[2][1] >= solution.fill_levels[1] + 1


@pytest.mark.parametrize(
    ("shared_id", "reverse_geometry", "second_band"),
    [(False, True, 0), (True, False, 0), (True, True, 1)],
)
def test_non_twins_stay_independent(shared_id, reverse_geometry, second_band):
    second_coords = (
        [(100, 0), (0, 0)] if reverse_geometry else [(0, 0), (100, 0)]
    )
    forward_properties = {"edge_ref": "forward"}
    reverse_properties = {"edge_ref": "second"}
    if shared_id:
        forward_properties["road_id"] = "road-1"
        reverse_properties["road_id"] = "road-1"
    forward = Corridor(
        geometry=LineString([(0, 0), (100, 0)]),
        band=0,
        properties=forward_properties,
    )
    reverse = Corridor(
        geometry=LineString(second_coords),
        band=second_band,
        properties=reverse_properties,
    )
    order = [{
        "pair_id": "keep-directions-independent",
        "relation": "order",
        "edge_a": "second",
        "edge_b": "forward",
        "node_ref": "",
        "endpoint_a": "",
        "endpoint_b": "",
        "upper_edge_ref": "second",
        "lower_edge_ref": "forward",
        "enabled": "true",
    }]

    solution = solve_stacking([forward, reverse], pair_table=order)

    assert solution.info["direction_twin_count"] == 0
    assert solution.fill_levels[1] > solution.fill_levels[0]
