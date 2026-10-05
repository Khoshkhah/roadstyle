"""Tests for persistent road-pair input and override tables."""

from shapely.geometry import LineString

from roadstyle.v2.engine.pairs import (
    discover_pair_table,
    merge_pair_overrides,
    read_pair_table,
    write_pair_table,
)
from roadstyle.v2.engine.primitives import Corridor
from roadstyle.v2.engine.solver import solve_stacking, write_pair_tables


def _crossing_roads():
    return [
        Corridor(
            id="ground",
            geometry=LineString([(-50, 0), (50, 0)]),
            band=0,
            properties={"edge_ref": "ground"},
        ),
        Corridor(
            id="bridge",
            geometry=LineString([(0, -50), (0, 50)]),
            band=1,
            properties={"edge_ref": "bridge"},
        ),
    ]


def test_discover_pair_table_records_crossing_relationship():
    rows = discover_pair_table(_crossing_roads())

    crossing = [row for row in rows if row["relation"] == "cross"]
    assert len(crossing) == 1
    assert crossing[0]["upper_edge_ref"] == "bridge"
    assert crossing[0]["lower_edge_ref"] == "ground"
    assert crossing[0]["enabled"] == "true"


def test_override_can_reverse_pair_order_used_by_solver():
    corridors = _crossing_roads()
    original = discover_pair_table(corridors)
    crossing = next(row for row in original if row["relation"] == "cross")
    override = {
        "action": "replace",
        "pair_id": crossing["pair_id"],
        "upper_edge_ref": "ground",
        "lower_edge_ref": "bridge",
    }
    effective = merge_pair_overrides(original, [override])
    sol = solve_stacking(corridors, pair_table=effective, head_m=5.0)

    assert sol.fill_levels[0] > sol.fill_levels[1]


def test_pair_tables_round_trip_and_override_file(tmp_path):
    corridors = _crossing_roads()
    original_path = tmp_path / "road_pairs_original.csv"
    override_path = tmp_path / "road_pairs_overrides.csv"
    write_pair_tables(corridors, original_path, override_path)

    original = read_pair_table(original_path)
    assert original
    assert read_pair_table(override_path, overrides=True) == []
    crossing = next(row for row in original if row["relation"] == "cross")
    write_pair_table(
        override_path,
        [{
            "action": "replace",
            "pair_id": crossing["pair_id"],
            "upper_edge_ref": "ground",
            "lower_edge_ref": "bridge",
        }],
        overrides=True,
    )

    result = solve_stacking(
        _crossing_roads(),
        pair_table=original_path,
        pair_overrides=override_path,
        head_m=5.0,
    )
    assert result.fill_levels[0] > result.fill_levels[1]
